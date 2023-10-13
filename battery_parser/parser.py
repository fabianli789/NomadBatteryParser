#
# Copyright The NOMAD Authors.
#
# This file is part of NOMAD. See https://nomad-lab.eu for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import os
import re
import datetime
import numpy as np
from pathlib import Path

from nomad.datamodel import EntryArchive
from nomad.parsing import MatchingParser
from nomad.units import ureg as units
from nomad.datamodel.metainfo.simulation.run import Run, Program
from nomad.datamodel.metainfo.simulation.system import System
from nomad.datamodel.metainfo.simulation.calculation import Calculation, Energy, EnergyEntry
from nomad.datamodel.metainfo.workflow import Workflow
from nomad.datamodel.results import Results, Properties, Structure
from nomad.parsing.file_parser import UnstructuredTextFileParser, Quantity
from nomad.datamodel.optimade import Species
from . import metainfo  # pylint: disable=unused-import
from .metainfo.battery import Dimensions, ChemReactions, Concentrations, Time


def DetailedParser(filepath, archive):
    with open(str(filepath.parent) + r'/status.csv') as status_file:
        time_run = archive.m_setdefault("run.time_run")
        time_run.cpu1_start = 0
        calc = archive.m_setdefault("run.calculation")
        
        for i, line in enumerate(status_file):
            line = line.strip("\n")
            parts = line.split(",")
            if parts[0] == None:
                continue
            if re.search(r"CPU", parts[0]):
                time_run.cpu1_end = parts[1]
            if re.search(r'KMC time', parts[0]):
                calc.time = parts[1]
            if re.search(r'steps', parts[0]):
                calc.step = int(float(parts[1]))

    with open(str(filepath.parent) + r'/SEI_properties.csv') as prop_file:
        dim = calc.m_create(Dimensions)

        for i, line in enumerate(prop_file):
            line = line.strip("\n")
            parts = line.split(",")
            if parts[0] == None:
                continue
            if re.search(r'Thickness', parts[0]):
                dim.thickness = float(parts[1])    
            if re.search(r'Volume', parts[0]):
                calc.volume_fraction = float(parts[1])
            if re.search(r'Poro', parts[0]):
                calc.porosity = float(parts[1])

    with open(str(filepath.parent) + r"/occurrence_res.csv") as occurrence_file:
        occurence_array = []
        residence_time_array = []
        for i, line in enumerate(occurrence_file):
            if re.search("Occurrences", line):
                continue
            part1, part2, part3 = line.split(",")
            occurence_array.append(int(part2))
            residence_time_array.append(float(part3))
    
    with open(str(filepath.parent) + r'/concentration.csv') as conc_file:
        first_line_parts = conc_file.readline().strip("\n").split(",")
        for x, bla in enumerate(conc_file):
            rows = x
        conc_array = np.zeros((rows+1, len(first_line_parts)-2))
        time_array = []

    with open(str(filepath.parent) + r'/concentration.csv') as conc_file:    
        for j, line in enumerate(conc_file):
    
            if re.search(r'time', line):
                continue
            
            parts = line.strip("\n").split(",")
            parts = [float(x) for x in parts]
            time_array.append(parts[-1])
            parts = parts[1:-1]            
            conc_array[j-1] = parts

        calc.concentration_time = time_array
        
        for i in range(len(first_line_parts)-2):
            conc = calc.m_create(Concentrations)   
            conc.name = first_line_parts[i+1]
            conc.concentration = conc_array[:,i] 
    
    with open(str(filepath.parent) + r'/input_battery.yml') as file:
            j = 0
            for i, line in enumerate(file):
                parts  = line.split(": ")
                if parts[0] == "T":
                    
                    calc.temperature = parts[1]
                elif parts[0] == "xdim":
                    dim.x = float(parts[1])
                elif parts[0] =="ydim":
                    dim.y = float(parts[1])
                elif re.search(r'\-', parts[0]):
                    chem_reactions = calc.m_create(ChemReactions)
                    parts[0] = parts[0].lstrip('- ').rstrip(' ')
                    chem_reactions.name = parts[0]
                    if re.search(r'escape', parts[0]):
                            
                        escaped = Escaped(Path(filepath).parent, chem_reactions)
                        chem_reactions.escaped = escaped[j]
                        j += 1
                    chem_reactions.barrier = float(parts[1])
                    
                    chem_reactions.occurences = occurence_array[i-5]
                    chem_reactions.residence_time = residence_time_array[i-5]
    with open(str(filepath.parent) + r'/last_step.csv') as last_step_file:
        species_array = []
        for j, x in enumerate(last_step_file):
            pass
        coordinates = np.zeros((j, 3))
        coord_x = []
        coord_y = []
    with open(str(filepath.parent) + r'/last_step.csv') as last_step_file:    
        for i, line in enumerate(last_step_file):
            parts = line.strip("\n").split(",")
            if re.search(r'species', parts[3]):
                continue
            coord_x.append(float(parts[1].strip('"').strip("[")))
            coord_y.append(float(parts[2].strip('"').strip("]")))


            species_array.append(parts[3])
        coordinates[:, 0] = coord_x
        coordinates[:, 1] = coord_y
        structure_original = archive.m_setdefault("results.properties.structures.structure_original")
        structure_original.cartesian_site_positions = coordinates
        structure_original.species_at_sites = species_array
        species_unique = list(set(species_array))
        
        for x in range(len(species_unique)):    
            sec_species = structure_original.m_create(Species)
            sec_species.name = species_unique[x]
            sec_species.chemical_symbols = []
            if re.search(r'C', species_unique[x]) and not re.search(r'EDC', species_unique[x]):
                sec_species.chemical_symbols.append("C")
            if re.search(r'SEI cluster', species_unique[x]):
                sec_species.name = species_unique[x] + " (cluster = more than 2 Li2EDC molecules)"
                sec_species.chemical_symbols.append("H")
                sec_species.chemical_symbols.append("C")
                sec_species.chemical_symbols.append("O")
                sec_species.chemical_symbols.append("Li")           
            if re.search(r'EDC', species_unique[x]):
                sec_species.name = species_unique[x] + " (EDC = ethylene dicarbonate)"
                sec_species.chemical_symbols.append("H")
                sec_species.chemical_symbols.append("C")
                sec_species.chemical_symbols.append("O")
            if re.search(r'Li', species_unique[x]):
                sec_species.chemical_symbols.append("Li")
            if re.search(r'O', species_unique[x]):
                sec_species.chemical_symbols.append("O")
def Escaped(parent, chem_reactions):
    escaped_file =str(parent)+r"/escaped.csv"
    with open(escaped_file) as file:
        escaped_array = []
        for i, line in enumerate(file):
            parts =  line.strip("\n").split(",")
            if len(parts) ==  0 or len(parts) == 1:
                continue
            
            escaped_array.append(int(parts[1])) 
    return escaped_array        

                        

class BatteryParser():

    def parse(self, filepath, archive, logger):
        input_run = archive.m_create(Run)
        input_run.program_name = 'Meysam Battery Parser'
        input_run.program = Program(name='Meysam Battery Parser')

        mainfile = Path(filepath)
        DetailedParser(mainfile, archive)
