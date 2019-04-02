import json
import uuid
from copy import copy, deepcopy
from datetime import datetime
from functools import partial
from glob import glob
from itertools import chain, combinations
from pathlib import Path
from warnings import warn

import networkx as nx
import pandas as pd

from . import OUTPUT_DIRECTORY, PATTERNS
from .graph_objects import DiEdge, PropertyDiGraph, Vertex
from .utils import (associate_node_id, associate_node_types_settings,
                    associate_predecessors, associate_renames,
                    associate_successors, build_dict,
                    create_column_values_singleton, create_column_values_space,
                    create_column_values_under, make_object, match_changes,
                    remove_duplicates, to_excel_df, truncate_microsec)


class Manager:
    """
    Class for raw data input and distribution to other classes.

    The Manager takes in a list of n excel filepaths and a single json_path.
    The first Excel file in the excel_path input variable is assumed to be the
    baseline to which all subsequent excel paths will be compared as ancestors.
    If a comparison is not desired then each Excel file will be analyzed
    independently to produce create instructions for the Player Piano.

    A single json_path is taken because all of the input excel files are
    assumed to be of the same type and thus to correspond to the same set of
    data keys.

    Attribtues
    ----------
    excel_path : list
        list of paths to Excel Files.

    json_path : string
        string representing a path to a *.json file that is the key to decoding
        the Excel inputs into MagicDraw compatiable outputs.

    json_data : dictionary
        The json data associated with the json_path.

    translator : MDTranslator
        The MDTranslator object which can be passed to classes that require its
        functionality.

    evaluators : Evaluator
        list of the Evaluators created for each Excel file in the excel_path.
        len(evaluators) == len(excel_path)
    """

    def __init__(self, excel_path=None, json_path=None):
        self.excel_path = excel_path
        self.json_path = json_path
        self.json_data = None
        self.get_json_data()
        self.translator = MDTranslator(json_data=self.json_data)
        self.evaluators = []
        self.create_evaluators()

    def get_json_data(self):
        json_path = Path(self.json_path)
        data = (json_path).read_text()
        data = json.loads(data)
        self.json_data = data

    def create_evaluators(self):
        # TODO: Give baseline translator to change files but also to create
        # files if multiple create files in a create command. Issue?
        path_name = [excel_file.name for excel_file in self.excel_path]

        for count, excel_file in enumerate(self.excel_path):
            if count != 0:
                translator = self.evaluators[0].translator
            else:
                translator = self.translator
            self.evaluators.append(
                Evaluator(excel_file=excel_file,
                          translator=deepcopy(translator)))

    def get_pattern_graph_diff(self, out_directory=''):
        """
        Compares the graph describing an Original MagicDraw model to the graph
        describing an Updated MagicDraw model. This method only compares an
        original graph instance to a chagne instance, i.e. it ignores change
        to change comparisons.

        This function creates an edge set for all the edges in the original
        and the change graph and removes all common edges. Then it builds a
        dictionary paring each remaining original edge to all of the change
        edges of the same type. After building the dicitionary,

        Parameters
        ----------
        out_directory : string
            Desired directory for the output files. The directory specified
            here will be pushed to the json and excel writing functions.

        Notes
        -----
        For each pair of Evaluators such that one Evaluator is the original and
        the other Evaluator has a Rename DataFrame the function compares their
        graphs for differences. First, the function identifies the updated
        file and gets the new name information and builds a rename dictionary
        to then replace the objects that have changed names with the names
        from the original file.

        After masking the new names with their corresponding old name the edges
        from both graphs are arranged into dictionary by edge type; removing
        edges shared by both the original and changed alon gthe way.

        Once prepared, the match_changes function preforms a version of the
        stable marriage algorithm to pair off the changes and identify any
        changes where the desired change is unclear.

        Finally, the algorithm puts everything back in place and sends the
        changes to JSON creation and Excel creation.

        See Also
        --------
        match_changes
        """
        evaluator_dict = {evaluator: index for index, evaluator in enumerate(
            self.evaluators
        )}
        self.evaluator_change_dict = {}
        orig_eval = self.evaluators[0]

        for pair in combinations(self.evaluators, 2):
            # Checking if Evaluator has a rename dataframe
            if pair[0].has_rename and pair[1].has_rename:  # comparing changes
                continue  # skip because this is comparing diff to diff

            eval_1_e_dict = pair[0].prop_di_graph.edge_dict
            eval_2_e_dict = pair[1].prop_di_graph.edge_dict

            edge_set_one = pair[0].edge_set  # get baseline edge set
            edge_set_two = pair[1].edge_set  # get the changed edge set

            # remove common edges
            # have to do this with named edges.
            # TODO: implement __eq__ and __neq__ methods to the DiEdge then
            # these set operations can be done without casting to str then
            # casting back.
            edge_set_one_set = {edge.named_edge_triple
                                for edge in edge_set_one}
            edge_set_two_set = {edge.named_edge_triple
                                for edge in edge_set_two}

            # Remove edges common to each but preserve set integrity for
            # each evaluator
            eval_one_unmatched_named = list(edge_set_one_set.difference(
                edge_set_two_set))
            eval_two_unmatched_named = list(edge_set_two_set.difference(
                edge_set_one_set
            ))

            # Organize edges in dictionary based on type (this goes on for
            # multiple lines)
            eval_one_unmatched = [eval_1_e_dict[edge]
                                  for edge in eval_one_unmatched_named]
            eval_two_unmatched = [eval_2_e_dict[edge]
                                  for edge in eval_two_unmatched_named]

            eval_one_unmatch_map = dict((edge.edge_attribute, list())
                                        for edge in eval_one_unmatched)
            eval_two_unmatch_map = dict((edge.edge_attribute, list())
                                        for edge in eval_two_unmatched)

            for edge in eval_one_unmatched:
                eval_one_unmatch_map[edge.edge_attribute].append(
                    edge)
            for edge in eval_two_unmatched:
                eval_two_unmatch_map[edge.edge_attribute].append(
                    edge)

            eval_one_unmatch_pref = {}
            eval_two_unmatch_pref = {}

            ance_keys_not_in_base = set(
                eval_two_unmatch_map.keys()).difference(
                    set(eval_one_unmatch_map))

            eval_one_unmatch_pref['Added'] = []
            eval_one_unmatch_pref['Deleted'] = []
            for edge_type in ance_keys_not_in_base:
                eval_one_unmatch_pref['Added'].extend(
                    eval_two_unmatch_map[edge_type])

            for edge in eval_one_unmatched:
                if edge.edge_attribute not in eval_two_unmatch_map.keys():
                    eval_one_unmatch_pref['Deleted'].append(edge)
                else:
                    eval_one_unmatch_pref[edge] = copy(eval_two_unmatch_map[
                        edge.edge_attribute])
            for edge in eval_two_unmatched:
                if edge.edge_attribute not in eval_one_unmatch_map.keys():
                    eval_two_unmatch_pref[edge] = []
                else:
                    eval_two_unmatch_pref[edge] = copy(eval_one_unmatch_map[
                        edge.edge_attribute])

            # Run the matching algorithm
            # Always expect the input dict to be Original: Chagnes.
            # Functions down the line hold this expectation.
            eval_one_matches = match_changes(
                change_dict=eval_one_unmatch_pref)

            changes_and_unstable = {'Changes': eval_one_matches[0],
                                    'Unstable Pairs': eval_one_matches[1]}

            key = '{0}-{1}'.format(evaluator_dict[pair[0]],
                                   evaluator_dict[pair[1]])

            self.graph_difference_to_json(change_dict=eval_one_matches[0],
                                          translator=pair[1].translator,
                                          evaluators=key,
                                          out_directory=out_directory)
            self.evaluator_change_dict.update(
                {key: changes_and_unstable})

        return self.evaluator_change_dict

    def changes_to_excel(self, out_directory=''):
        """
        Write the changes from the get_pattern_graph_diff() method to an Excel
        file. The changes displayed in the file are intended to inform the user
        of the changes that the change_json will make to the model when
        implemented in MagicDraw and to display the changes that the user will
        have to make on their own to bring the model up to date. In other words
        the Excel file generated here displays the complete set of differences
        between the original and the change file and the likely changes that
        update the original file to be equivalent with the specified change
        file. This method produces an Excel file by flattening the
        evaluator_change_dict variable and writing it to a Python dictionary,
        which can be interpreted as a Pandas DataFrame and written out to an
        Excel file.

        Parameters
        ----------
        out_directory : str
            string representation of the desired output directory. If
            out_directory is not specified then the output directory will by
            the same as the input directory.

        Notes
        -----
        This function could be expanded to produce a more "readable" Excel
        file. Currently it just produces a "raw" Excel file, which becomes
        particularly apparent when viewing the Unstable Matches Original
        and Unstable Matches Change columns of the Excel, as a background on
        the idea of the Stable Marriage Algorithm helps interpret the displayed
        data.

        See Also
        --------
        get_pattern_graph_diff() for the generation of the match dictionary
        to_excel_df() for the process of transforming the dictionary into a
        DataFrame.
        """
        # TODO: When length of value > 1 put these changes into
        # Unstable Original: [key*len(value)] Unstable Change: [value]
        for key in self.evaluator_change_dict:
            outfile = Path(
                'Model Diffs {0}-{1}.xlsx'.format(
                    key, truncate_microsec(curr_time=datetime.now().time())))

            if out_directory:
                outdir = out_directory
            else:
                outdir = OUTPUT_DIRECTORY

            difference_dict = self.evaluator_change_dict[key]
            input_dict = {}
            evals_comp = key.split('-')
            edit_left_dash = 'Edit {0}'.format(str(int(evals_comp[0]) + 1))
            edit_right_dash = 'Edit {0}'.format(str(int(evals_comp[-1]) + 1))
            column_headers = [edit_left_dash, edit_right_dash]

            for in_key in difference_dict:
                if not difference_dict[in_key]:
                    continue
                column_headers.append(in_key)
                input_dict.update(difference_dict[in_key])
            df_data = to_excel_df(data_dict=input_dict,
                                  column_keys=column_headers)

            df_output = pd.DataFrame(data=dict([
                (k, pd.Series(v)) for k, v in df_data.items()
            ]))

            df_output.to_excel(
                (outdir / outfile), sheet_name=key, index=False)

    def graph_difference_to_json(self, change_dict=None, translator=None,
                                 evaluators='', out_directory='', ):
        """
        Produce MagicDraw JSON instruction for Player Piano from the
        confidently identified changes. This method returns a change list,
        Python list of dictionaries containing MagicDraw instructions, and
        a JSON file in the out_directory, if provided otherwise in the same
        directory as the input files. JSON instructions created for
        Added edges, Deleted edges and changed edges. For Added edges, if the
        source and target nodes have already been created during this function
        call then just provide instructions to create the new edges, otherwise
        create the source and target nodes then link them with an edge. For
        all Deleted edges, each edge in the list receives a delete operation
        intentionally leaving the source and target nodes in the model incase
        they fulfill other roles. Changed edges have two main categories with
        three subcategories. First, a change edge can either involve a renamed
        source or target node or a newly created source or target node. Once
        identified as a rename (respectively newly created), the edge is
        sorted into three scenarios, both the source and target node represent
        renamed (respectively new) nodes, or the source or target node
        corresponds to a rename (respectively new) node operation. After
        identifying all of the changes and producing the associated
        dictionaries, the operations are sorted to place created nodes and
        their decorations first, followed by deleted edges, renamed nodes and
        ending with added edges.

        Parameters
        ----------
        change_dict : dict
            Dictionary of confident changes. Two static keys 'Added' and
            'Deleted' with associated lists of added and deleted nodes
            respectively. The remaining key value pairs in the change_dict
            represent confident changes with the key being an edge from the
            original Evaluator and the value being a list comprised of the
            likely change edge.

        translator : MDTranslator
            MagicDraw Translator object associated with the current update
            evaluator.

        evaluators : str
            Number of the two evaluators under consideration. The original
            evaulator always receives the numebr 0 while each change evaluator
            has a number 1-n with n being the nth evaluator.

        out_directory : str
            String specifying the output directory

        Notes
        -----
        Any edge not meeting one of the eight criteria defined will fall
        through to the else case and become an edge replace operation.
        The get_pattern_graph_diff() method automatically calls this method.
        """
        # need to strip off the keys that are strings and use them to
        # determine what kinds of ops I need to preform.
        # Naked Key: Value pairs mean delete edge key and add value key.
        # Purposefully excluding unstable pairs because the Human can make
        # those changes so they are clear.
        static_keys = ['Added', 'Deleted', ]
        change_list = []
        edge_del = []
        edge_add = []
        node_renames = []
        create_node = []
        node_dec = []
        # should the seen ids initially be populated with ids in translator
        # that are not uuid.uuid4() objects.
        # set(filter(
        # lambda x: not isinstance(x, uuid.uuid4()), translator.uml_id.keys()))
        seen_ids = set()
        for k, v in translator.uml_id.items():
            if isinstance(v, str):
                seen_ids.add(v)

        for key, value in change_dict.items():
            if key == 'Added':
                for edge in value:
                    edge_source, edge_target = edge.source, edge.target
                    # if source or target id in seen ids then do below
                    # else (both source and target in seen ids then just add
                    # the edge (the floating add edge under the else statment)
                    if edge_source.id not in seen_ids:
                        seen_ids.add(edge_source.id)
                        s_cr, s_dec, s_edg = edge_source.create_node_to_uml(
                            translator=translator)
                        create_node.extend(s_cr)
                        node_dec.extend(s_dec)
                        edge_add.extend(s_edg)
                    if edge_target.id not in seen_ids:
                        seen_ids.add(edge_target.id)
                        t_cr, t_dec, t_edg = edge_target.create_node_to_uml(
                            translator=translator)
                        create_node.extend(t_cr)
                        node_dec.extend(t_dec)
                        edge_add.extend(t_edg)
                    edge_add.append(edge.edge_to_uml(op='replace',
                                                     translator=translator))
            elif key == 'Deleted':
                for edge in value:
                    edge_del.append(edge.edge_to_uml(op='delete',
                                                     translator=translator))
            else:
                source_val, target_val = value[0].source, value[0].target
                # Using filter as mathematical ~selective~ or.
                eligible = list(filter(lambda x: x.id not in seen_ids,
                                       [source_val, target_val]))
                has_rename = list(
                    filter(lambda x: x.has_rename, eligible))
                is_new = list(
                    filter(lambda x: isinstance(x.id, type(uuid.uuid4())),
                           eligible))
                if has_rename:
                    for node in has_rename:
                        seen_ids.add(node.id)
                        node_renames.append(
                            node.change_node_to_uml(translator=translator))
                    else:
                        edge_add.append(
                            value[0].edge_to_uml(
                                op='replace', translator=translator))
                if is_new:
                    for node in is_new:
                        seen_ids.add(node.id)
                        n_cr, n_dec, n_edg = node.create_node_to_uml(
                            translator=translator)
                        create_node.extend(n_cr)
                        node_dec.extend(n_dec)
                        edge_add.extend(n_edg)
                    else:
                        edge_add.append(
                            value[0].edge_to_uml(
                                op='replace', translator=translator))
                if not has_rename and not is_new:
                    edge_add.append(
                        value[0].edge_to_uml(
                            op='replace', translator=translator))

        if create_node:
            change_list.extend(remove_duplicates(create_node, create=True))
            change_list.extend(remove_duplicates(node_dec))
        change_list.extend(remove_duplicates(edge_del))
        change_list.extend(remove_duplicates(node_renames))

        # change_list.extend(list(e_a_dict.values()))

        json_out = {'modification targets': []}
        json_out['modification targets'].extend(change_list)
        outfile = Path('graph_diff_changes_{0}({1}).json'.format(
            evaluators, truncate_microsec(curr_time=datetime.now())))

        if out_directory:
            outdir = out_directory
        else:
            outdir = OUTPUT_DIRECTORY

        (outdir / outfile).write_text(
            json.dumps(json_out, indent=4, sort_keys=True))

        return change_list


class Evaluator:
    """Class for creating the PropertyDiGraph from the Excel data with the help
    of the MDTranslator.

    Evaluator produces a Pandas DataFrame from the Excel path provided by the
    Manager. The Evaluator then updates the DataFrame with column headers
    compliant with MagidDraw and infers required columns from the data stored
    in the MDTranslator. With the filled out DataFrame the Evaluator produces
    the PropertyDiGraph.

    Parameters
    ----------
    excel_file : string
        String to an Excel File

    translator : MDTranslator
        MDTranslator object that holds the data from the *.json file
        associated with this type of Excel File.

    Attributes
    ----------
    df : Pandas DataFrame
        DataFrame constructed from reading the Excel File.

    prop_di_graph : PropertyDiGraph
        PropertyDiGraph constructed from the data in the df.

    root_node_attr_columns : set
        Set of column names in the initial read of the Excel file that do not
        appear as Vertices in the MDTranslator definition of the expected
        Vertices. The columns collected here will later be associated to the
        corresponding root node as additional attributes.

    Properties
    ----------
    named_vertex_set : set
        Returns the named vertex set from the PropertyDiGraph.

    vertex_set : set
        Returns the vertex set from the PropertyDiGraph
    """

    # TODO: Consider moving function calls into init since they should be run
    # then
    def __init__(self, excel_file=None, translator=None):
        self.translator = translator
        self.df = pd.DataFrame()
        self.df_ids = pd.DataFrame()
        self.df_renames = pd.DataFrame()
        self.excel_file = excel_file
        # TODO: Why did I do this? save the file off as self.file then
        # call sheets_to_dataframe on self.
        self.sheets_to_dataframe(excel_file=excel_file)
        # self.df.dropna(how='all', inplace=True)
        self.prop_di_graph = None
        self.root_node_attr_columns = set()

    @property
    def has_rename(self):
        if not self.df_renames.empty:
            return True
        else:
            return False

    def sheets_to_dataframe(self, excel_file=None):
        # TODO: Generalize/Standardize this function
        patterns = [pattern.name.split('.')[0].lower()
                    for pattern in PATTERNS.glob('*.json')]
        ids = ['id', 'ids', 'identification number',
               'id number', 'uuid', 'mduuid', 'magicdraw id',
               'magic draw id', 'magicdraw identification',
               'identification numbers', 'id_numbers', 'id_number']
        renames = ['renames', 'rename', 'new names', 'new name', 'newnames',
                   'newname', 'new_name', 'new_names', 'changed names',
                   'changed name', 'change names', 'changed_names',
                   'changenames', 'changed_names']
        xls = pd.ExcelFile(excel_file, on_demand=True)
        for sheet in sorted(xls.sheet_names):  # Alphabetical sort
            # Find the Pattern Sheet
            if any(pattern in sheet.lower() for pattern in patterns):
                # Maybe you named the ids sheet Pattern IDs I will find it
                if any(id_str in sheet.lower() for id_str in ids):
                    self.df_ids = pd.read_excel(
                        excel_file, sheet_name=sheet)
                    self.df_ids.set_index(
                        self.df_ids.columns[0], inplace=True)
                    self.translator.uml_id.update(
                        self.df_ids.to_dict(
                            orient='dict')[self.df_ids.columns[0]])
                # elif sheet.lower() in renames:
                # Maybe you named the rename sheet Pattern Renames
                elif any(renm_str in sheet.lower() for renm_str in renames):
                    self.df_renames = pd.read_excel(
                        excel_file, sheet_name=sheet)
                    self.df_renames.dropna(
                        how='all', inplace=True)
                    for row in self.df_renames.itertuples(index=False):
                        if row[0] in self.translator.uml_id.keys():
                            # replace instances of this with those in 1
                            if len(row) == 2:
                                if not self.df_renames.index.is_object():
                                    # do the thing set the index as new name
                                    old_mask = self.df_renames == row[0]
                                    old_masked_df = self.df_renames[
                                        old_mask].dropna(how='all', axis=0)
                                    # should return new names col and nan
                                    new_names = self.df_renames.T.index.where(
                                        old_masked_df.isnull()).tolist()
                                    new_col = list(
                                        chain.from_iterable(new_names))
                                    new_name = list(
                                        filter(
                                            lambda x: isinstance(
                                                x, str), new_col))
                                    self.df_renames.set_index(
                                        new_name, inplace=True)
                            else:
                                raise RuntimeError(
                                    'Unexpected columns in Rename Sheet. \
                                     Expected 2 but found more than 2.')
                            self.df.replace(to_replace=row[0],
                                            value=row[1],
                                            inplace=True)
                            self.translator.uml_id.update({
                                row[1]: self.translator.uml_id[row[0]]
                            })
                        elif row[1] in self.translator.uml_id.keys():
                            if len(row) == 2:
                                if not self.df_renames.index.is_object():
                                    # do the thing set the index as new name
                                    old_mask = self.df_renames == row[1]
                                    old_masked_df = self.df_renames[
                                        old_mask].dropna(how='all', axis=0)
                                    # should return new names col and nan
                                    new_names = self.df_renames.T.index.where(
                                        old_masked_df.isnull()).tolist()
                                    new_col = list(
                                        chain.from_iterable(new_names))
                                    new_name = list(
                                        filter(
                                            lambda x: isinstance(
                                                x, str), new_col))
                                    self.df_renames.set_index(
                                        new_name, inplace=True)
                            else:
                                raise RuntimeError(
                                    'Unexpected columns in Rename Sheet. \
                                     Expected 2 but found more than 2.')
                            # same as above in other direction
                            self.df.replace(to_replace=row[1],
                                            value=row[0],
                                            inplace=True)
                            self.translator.uml_id.update(
                                {row[0]: self.translator.uml_id[row[1]]}
                            )
                else:
                    self.df = pd.read_excel(excel_file, sheet_name=sheet)
                    self.df.dropna(how='all', inplace=True)
            # elif sheet.lower() in renames:
            # Hopefully you explcitly named the Rename sheet
            elif any(renm_str in sheet.lower() for renm_str in renames):
                self.df_renames = pd.read_excel(excel_file,
                                                sheet_name=sheet)
                self.df_renames.dropna(
                    how='all', inplace=True)
                index_name = ''
                for row in self.df_renames.itertuples(index=False):
                    if all(row[i] in self.translator.uml_id.keys()
                            for i in (0, 1)):
                        raise RuntimeError('Both old and new in keys')
                    elif row[0] in self.translator.uml_id.keys():
                        # then replace instances of this with those in 1
                        if len(row) == 2:
                            if not self.df_renames.index.is_object():
                                # do the thing set the index as new name
                                old_mask = self.df_renames == row[0]
                                old_masked_df = self.df_renames[
                                    old_mask].dropna(how='all', axis=0)
                                # should return name of new names col and nan
                                new_names = self.df_renames.T.index.where(
                                    old_masked_df.isnull()).tolist()
                                new_col = list(
                                    chain.from_iterable(new_names))
                                new_name = list(
                                    filter(
                                        lambda x: isinstance(x, str), new_col))
                                self.df_renames.set_index(
                                    new_name, inplace=True)
                        else:
                            raise RuntimeError(
                                'Unexpected columns in Rename Sheet. \
                                 Expected 2 but found more than 2.')
                        self.df.replace(to_replace=row[0], value=row[1],
                                        inplace=True)
                        self.translator.uml_id.update({
                            row[1]: self.translator.uml_id[row[0]]
                        })
                        continue
                    elif row[1] in self.translator.uml_id.keys():
                        # row[1] is old, row[0] is new
                        if len(row) == 2:
                            if not self.df_renames.index.is_object():
                                # do the thing set the index as new name
                                old_mask = self.df_renames == row[1]
                                old_masked_df = self.df_renames[
                                    old_mask].dropna(how='all', axis=0)
                                # should return name of new names col and nan
                                new_names = self.df_renames.T.index.where(
                                    old_masked_df.isnull()).tolist()
                                new_col = list(
                                    chain.from_iterable(new_names))
                                new_name = list(
                                    filter(
                                        lambda x: isinstance(x, str), new_col))
                                self.df_renames.set_index(
                                    new_name, inplace=True)
                        else:
                            raise RuntimeError(
                                'Unexpected columns in Rename Sheet. \
                                 Expected 2 but found more than 2.')
                        # same as above in other direction
                        self.df.replace(to_replace=row[1], value=row[0],
                                        inplace=True)
                        self.translator.uml_id.update(
                            {row[0]: self.translator.uml_id[row[1]]}
                        )
                        continue
            elif any(id_str in sheet.lower() for id_str in ids) and \
                    not any(pattern in sheet.lower() for pattern in patterns):
                self.df_ids = pd.read_excel(
                    excel_file, sheet_name=sheet)
                self.df_ids.set_index(
                    self.df_ids.columns[0], inplace=True)
                self.translator.uml_id.update(
                    self.df_ids.to_dict(
                        orient='dict')[self.df_ids.columns[0]])
            else:
                raise RuntimeError(
                    'Unrecognized sheet names for: {0}'.format(
                        excel_file.name
                    ))

    def rename_df_columns(self):
        """Returns renamed DataFrame columns from their Excel name to their
        MagicDraw name. Any columns in the Excel DataFrame that are not in the
        json are recorded as attribute columns.
        """
        for column in self.df.columns:
            try:
                new_column_name = self.translator.get_col_uml_names(
                    column=column)
                self.df.rename(columns={column: new_column_name}, inplace=True)
            except KeyError:
                # We continue because these columns are additional data
                # that we will associate to the Vertex as attrs.
                self.root_node_attr_columns.add(column)

    def add_missing_columns(self):
        """Adds the missing column to the dataframe. These columns are ones
        required to fillout the pattern in the MDTranslator that were not
        specified by the user. The MDTranslator provides a template for naming
        these inferred columns.

        Notes
        -----
        Stepping through the function, first a list of column names that
        appear in the JSON but not the Excel are compiled by computing the
        difference between the expected column set from the Translator and the
        initial dataframe columns. Then those columns are sorted by length
        to ensure that longer column names constructed of multiple shorter
        columns do not fail when searching the dataframe.
            e.g. Suppose we need to construct the column
            A_composite owner_component. Sorting by length ensures that
            columns_to_create = ['component', 'composite owner',
            'A_composite owner_component']
        Then for each column name in columns to create, the column name is
        checked for particular string properties and the inferred column values
        are determined based on the desired column name.
        """
        # from a collection of vertex pairs, create all of the columns for
        # for which data is required but not present in the excel.
        columns_to_create = list(set(
            self.translator.get_pattern_graph()).difference(
            set(self.df.columns)))
        # TODO: Weak solution to the creation order problem.
        columns_to_create = sorted(columns_to_create, key=len)

        under = '_'
        space = ' '
        dash = '-'
        if columns_to_create:
            for col in columns_to_create:
                if under in col:
                    if dash in col:
                        col_data_vals = col.split(sep=under)
                        suffix = col_data_vals[-1].split(sep=dash)
                        first_node_data = self.df.loc[:, col_data_vals[1]]
                        second_node_data = self.df.loc[:, suffix[0]]
                        suff = dash + suffix[-1]
                        self.df[col] = create_column_values_under(
                            prefix=col_data_vals[0],
                            first_node_data=first_node_data,
                            second_node_data=second_node_data,
                            suffix=suff
                        )
                    else:
                        col_data_vals = col.split(sep=under)
                        first_node_data = self.df.loc[:, col_data_vals[1]]
                        second_node_data = self.df.loc[:, col_data_vals[2]]
                        self.df[col] = create_column_values_under(
                            prefix=col_data_vals[0],
                            first_node_data=first_node_data,
                            second_node_data=second_node_data,
                            suffix=''
                        )
                elif space in col:
                    col_data_vals = col.split(sep=space)
                    root_col_name = self.translator.get_root_node()
                    if col_data_vals[0] in self.df.columns:
                        first_node_data = self.df.loc[:, col_data_vals[0]]
                        second_node_data = [col_data_vals[-1]
                                            for i in range(
                                                len(first_node_data))]
                    else:
                        first_node_data = self.df.iloc[:, 0]
                        second_node_data = self.df.loc[:, root_col_name]
                    self.df[col] = create_column_values_space(
                        first_node_data=first_node_data,
                        second_node_data=second_node_data
                    )
                else:
                    col_data_vals = col
                    root_col_name = self.translator.get_root_node()
                    first_node_data = self.df.iloc[:, 0]
                    second_node_data = [
                        col for count in range(len(first_node_data))]
                    self.df[col] = create_column_values_singleton(
                        first_node_data=first_node_data,
                        second_node_data=second_node_data
                    )

    def to_property_di_graph(self):
        """Creates a PropertyDiGraph from the completely filled out dataframe.
        To achieve this, we loop over the Pattern Graph Edges defined in the
        JSON and take each pair of columns and the edge type as a source,
        target pair with the edge attribute corresponding to the edge type
        defined in the JSON.
        """
        self.prop_di_graph = PropertyDiGraph(
            root_attr_columns=self.root_node_attr_columns
        )
        for index, pair in enumerate(
                self.translator.get_pattern_graph_edges()):
            edge_type = self.translator.get_edge_type(index=index)
            self.df[edge_type] = edge_type
            df_temp = self.df[[pair[0], pair[1], edge_type]]
            GraphTemp = nx.DiGraph()
            GraphTemp = nx.from_pandas_edgelist(
                df=df_temp, source=pair[0],
                target=pair[1], edge_attr=edge_type,
                create_using=GraphTemp)
            self.prop_di_graph.add_nodes_from(GraphTemp.nodes)
            self.prop_di_graph.add_edges_from(GraphTemp.edges,
                                              edge_attribute=edge_type)

        pdg = self.prop_di_graph
        tr = self.translator

        # Est list of lists with dict for each node contaiing its name
        # node is already a string because of networkx functionality
        # idea is to build up kwargs to instantiate a vertex object.
        node_atters = [[{'name': node}
                        for node in list(pdg)]]

        # various functions required to get different vertex attrs
        # partialy instantiate each function so that each fn only needs node
        associate_funs = [partial(associate_node_id, tr),
                          partial(associate_successors, pdg),
                          partial(associate_predecessors, pdg),
                          partial(associate_node_types_settings, self.df,
                                  tr, self.root_node_attr_columns),
                          partial(associate_renames, self.df_renames, tr), ]

        # apply each function to each node.
        # map(function, iterable)
        for fun in associate_funs:
            fun_map = map(fun, list(pdg))
            node_atters.append(fun_map)

        # Partially bake a Vertex object to make it act like a function when
        # passed the attr dict. Atter dict built using map(build_dict, zip())
        # zip(*node_atters) unpacks the nested lists then takes one of ea attr
        # from the map obj stored there (map objs are iterables)
        vertex = partial(make_object, Vertex)
        for mp in map(vertex, map(build_dict, zip(*node_atters))):
            vert_tup = (mp.name, {mp.name: mp})
            # overwrites the original node in the graph to add an attribute
            # {'<name>': <corresponding vertex object>}
            pdg.add_node(vert_tup[0], **vert_tup[1])

        # build edges container
        edges = []
        for edge, data in pdg.edges.items():
            diedge = DiEdge(source=pdg.nodes[edge[0]][edge[0]],
                            target=pdg.nodes[edge[1]][edge[1]],
                            edge_attribute=data['edge_attribute'])
            # The inner key must be a string thus 'diedge' instead of
            # pdg.edges[edge][edge] which would mimic behavior for nodes
            # pdg.nodes[node][node]
            edges.append((edge, {'diedge': diedge}))
        for edge in edges:
            # unpack each edge and the edge attribute dict for the add_edge fn
            pdg.add_edge(*edge[0], **edge[1])

        # pdg has associated vertex obj and associated edge obj in edj dict.
        return pdg

    @property
    def named_vertex_set(self):
        return self.prop_di_graph.get_vertex_set_named(df=self.df)

    @property
    def vertex_set(self):
        return self.prop_di_graph.vertex_set

    @property
    def named_edge_set(self):
        return self.prop_di_graph.named_edge_set

    @property
    def edge_set(self):
        return self.prop_di_graph.edge_set


class MDTranslator:
    """
    Class to serve as the Rosetta Stone for taking column headers from the
    Excel input to the MagicDraw compatible output. More specifically, this
    class provides access to data in the JSON file allowing the Evaluator to
    determine which columns are required to fill out the pattern that are
    missing in the input Excel and to associate edge types along the directed
    edges. Furthermore, while the Vertex is packaged in to_uml_json() the
    translator provides metadata information required by MagicDraw for block
    creation keyed by the node_type.

    Parameters
    ----------
    data : dictionary
        The JSON data saved off when the Manager accessed the JSON file.
    """

    def __init__(self, json_data=None):
        self.data = json_data
        self.uml_id = {}

    def get_uml_id(self, name=None):
        """Returns the UML_ID for the corresponding vertex name provided. If the
        name provided does not exist as a key in the UML_ID dictionary than a
        new key is created using that name and the value increments with
        new_<ith new number>.

        Parameters
        ----------
        name : string
            The Vertex.name attribute

        Notes
        -----
        This will be updated to become a nested dictionary
        with the first key being the name and the inner key will be the
        new_<ith new number> key and the value will be the UUID created
        by MagicDraw.
        """
        # TODO: write test function for this
        if name in self.uml_id.keys():
            return self.uml_id[name]
        else:
            self.uml_id.update({name: uuid.uuid4()})
            return self.uml_id[name]

    def get_root_node(self):
        return self.data['Root Node']

    def get_cols_to_nav_map(self):
        return self.data['Columns to Navigation Map']

    def get_pattern_graph(self):
        return self.data['Pattern Graph Vertices']

    def get_pattern_graph_edges(self):
        return self.data['Pattern Graph Edges']

    def get_edge_type(self, index=None):
        return self.data['Pattern Graph Edge Labels'][index]

    def get_col_uml_names(self, column=None):
        return self.data['Columns to Navigation Map'][column][-1]

    def get_uml_metatype(self, node_key=None):
        return self.data['Vertex MetaTypes'][node_key]

    def get_uml_stereotype(self, node_key=None):
        return self.data['Vertex Stereotypes'][node_key]

    def get_uml_settings(self, node_key=None):
        uml_phrase = self.data['Vertex Settings'][node_key]

        try:
            uml_phrase.keys()
        except AttributeError:
            return node_key, uml_phrase

        key = next(iter(uml_phrase))
        return key, uml_phrase[key]
