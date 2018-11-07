import unittest
import pandas as pd
import networkx as nx

from copy import copy

from graph_analysis.graph_creation import MDTranslator

from graph_analysis.utils import (create_column_values_under,
                                  create_column_values_space,
                                  create_column_values_singleton,
                                  create_column_values,
                                  get_node_types_attrs,
                                  get_setting_node_name_from_df,
                                  match,
                                  match_changes,
                                  associate_node_ids,
                                  to_excel_df,
                                  get_new_column_name,
                                  replace_new_with_old_name,
                                  new_as_old,
                                  to_nto_rename_dict)
from graph_analysis.graph_objects import DiEdge, Vertex


class TestUtils(unittest.TestCase):

    def setUp(self):
        pass

    def test_create_column_values_under(self):
        data_dict = {
            'blockValue': ['Apple', 'Orange'],
            'value': ['Core', 'Skin'],
        }
        df = pd.DataFrame(data=data_dict)
        column_vals = create_column_values_under(
            prefix='C',
            first_node_data=df.loc[:, 'value'],
            second_node_data=df.loc[:, 'blockValue'],
        )
        expect_no_suffix = ['C_core_apple', 'C_skin_orange']
        self.assertListEqual(expect_no_suffix, column_vals)

        col_vals_suff = create_column_values_under(
            prefix='A',
            first_node_data=df.loc[:, 'value'],
            second_node_data=df.loc[:, 'blockValue'],
            suffix='-end1'
        )
        expect_suffix = ['A_core_apple-end1', 'A_skin_orange-end1']
        self.assertListEqual(expect_suffix, col_vals_suff)

    def test_create_column_values_space(self):
        data_dict = {
            'composite owner': ['Car', 'Wheel'],
            'component': ['chassis', 'hub']
        }
        df = pd.DataFrame(data=data_dict)
        created_cols = create_column_values_space(
            first_node_data=df.loc[:, 'composite owner'],
            second_node_data=df.loc[:, 'component']
        )
        expect_space = ['car qua chassis context',
                        'wheel qua hub context']
        self.assertListEqual(expect_space, created_cols)

    def test_create_column_values_singleton(self):
        first_node_data = ['green', 'blue']
        second_node_data = ['context1', 'context1']
        created_cols = create_column_values_singleton(
            first_node_data=first_node_data,
            second_node_data=second_node_data
        )
        expectation = ['green context1', 'blue context1']
        self.assertListEqual(expectation, created_cols)

    def test_create_column_values(self):
        data = ['Car', 'Wheel', 'Engine']
        data_2 = ['chassis', 'hub', 'drive output']
        columns = ['A_"composite owner"_component', 'composite owner']
        expected_output = {'A_"composite owner"_component':
                           ['A_car_chassis', 'A_wheel_hub',
                            'A_engine_drive output'],
                           'composite owner':
                           ['car qua chassis context',
                            'wheel qua hub context',
                            'engine qua drive output context']
                           }
        for col in columns:
            list_out = create_column_values(col_name=col, data=data,
                                            aux_data=data_2)
            self.assertListEqual(expected_output[col], list_out)

    def test_get_node_types_attrs(self):
        data_dict = {
            'component': ['car', 'wheel', 'engine'],
            'Atomic Thing': ['Car', 'Wheel', 'Car'],
            'edge attribute': ['owner', 'owner', 'owner'],
            'Notes': ['little car to big Car',
                      6,
                      2]
        }
        df = pd.DataFrame(data=data_dict)

        node_type_cols, node_attr_dict = get_node_types_attrs(
            df=df, node='Car',
            root_node_type='Atomic Thing',
            root_attr_columns={'Notes'})

        attr_list = [{'Notes': 'little car to big Car'}, {'Notes': 2}]
        self.assertEqual({'Atomic Thing'}, node_type_cols)
        self.assertListEqual(attr_list,
                             node_attr_dict)

    def test_match_changes(self):
        base_inputs = [('s1', 't1', 'type'), ('s2', 't2', 'type'),
                       ('s3', 't3', 'owner'), ('s4', 't4', 'owner'),
                       ('s5', 't5', 'memberEnd'),
                       ('s6', 't6', 'memberEnd'),
                       ('s7', 't7', 'type'), ('s8', 't8', 'type'),
                       ('s9', 't9', 'owner'), ('s10', 't10', 'owner'),
                       ('s11', 't11', 'memberEnd'),
                       ('s12', 't12', 'memberEnd'),
                       ('song', 'tiger', 'blue'), ]

        ancestor = [('as1', 't1', 'type'), ('s2', 'at2', 'type'),
                    ('as3', 't3', 'owner'), ('s4', 'at4', 'owner'),
                    ('as5', 't5', 'memberEnd'),
                    ('s6', 'at6', 'memberEnd'),
                    ('as7', 't7', 'type'), ('s8', 'at8', 'type'),
                    ('as9', 't9', 'owner'), ('s10', 'at10', 'owner'),
                    ('as11', 't11', 'memberEnd'),
                    ('s12', 'at12', 'memberEnd'), ('b', 'c', 'orange'),
                    ('s1', 'at1', 'type')]

        base_edges = []
        ancestor_edges = []

        for edge_tuple in base_inputs:
            source = Vertex(name=edge_tuple[0])
            target = Vertex(name=edge_tuple[1])
            edge = DiEdge(source=source, target=target,
                          edge_attribute=edge_tuple[2])
            base_edges.append(edge)

        for edge_tuple in ancestor:
            source = Vertex(name=edge_tuple[0])
            target = Vertex(name=edge_tuple[1])
            edge = DiEdge(source=source, target=target,
                          edge_attribute=edge_tuple[2])
            ancestor_edges.append(edge)

        base_map = dict((ea.edge_attribute, list()) for ea in base_edges)

        ance_map = dict((ea.edge_attribute, list())
                        for ea in ancestor_edges)

        for edge in base_edges:
            base_map[edge.edge_attribute].append(edge)
        for edge in ancestor_edges:
            ance_map[edge.edge_attribute].append(edge)

        base_preference = {}
        ancestor_preference = {}

        ance_keys_not_in_base = set(
            ance_map.keys()).difference(set(base_map.keys()))

        base_preference['Added'] = []
        base_preference['Deleted'] = []
        for edge_type in ance_keys_not_in_base:
            base_preference['Added'].extend(ance_map[edge_type])

        for edge in base_edges:
            if edge.edge_attribute not in ance_map.keys():
                base_preference['Deleted'].append(edge)
            else:
                base_preference[edge] = copy(
                    ance_map[edge.edge_attribute])

        for edge in ancestor_edges:
            if edge.edge_attribute not in base_map.keys():
                ancestor_preference[edge] = []
            else:
                ancestor_preference[edge] = copy(
                    base_map[edge.edge_attribute])

        match_dict = match_changes(change_dict=base_preference, score={},
                                   match_ancestors={})

        expected_matches = {('s2', 't2', 'type'): ('s2', 'at2', 'type'),
                            ('s3', 't3', 'owner'): ('as3', 't3', 'owner'),
                            ('s4', 't4', 'owner'): ('s4', 'at4', 'owner'),
                            ('s5', 't5', 'memberEnd'):
                                ('as5', 't5', 'memberEnd'),
                            ('s6', 't6', 'memberEnd'):
                                ('s6', 'at6', 'memberEnd'),
                            ('s7', 't7', 'type'): ('as7', 't7', 'type'),
                            ('s8', 't8', 'type'): ('s8', 'at8', 'type'),
                            ('s9', 't9', 'owner'): ('as9', 't9', 'owner'),
                            ('s10', 't10', 'owner'):
                                ('s10', 'at10', 'owner'),
                            ('s11', 't11', 'memberEnd'):
                                ('as11', 't11', 'memberEnd'),
                            ('s12', 't12', 'memberEnd'):
                                ('s12', 'at12', 'memberEnd'),
                            'Added': [('b', 'c', 'orange'), ],
                            'Deleted': [('song', 'tiger', 'blue')]}

        expected_unstable = {('s1', 't1', 'type'):
                             [('as1', 't1', 'type'),
                              ('s1', 'at1', 'type')],
                             }
        pairings = match_dict[0]
        unstable_pairs = match_dict[1]
        pairings_str = {}
        pairings_str.update({'Deleted': []})
        pairings_str.update({'Added': []})

        unstable_keys = set(unstable_pairs.keys()).intersection(
            set(pairings.keys()))

        for key in pairings.keys():
            if key in unstable_keys:
                continue
            elif key not in ('Deleted', 'Added'):
                pairings_str.update({key.named_edge_triple:
                                     pairings[key][0].named_edge_triple})
            else:
                for edge in pairings[key]:
                    pairings_str[key].append(edge.named_edge_triple)

        self.assertDictEqual(expected_matches, pairings_str)

        for key in unstable_keys:
            unstable_key_vals = {
                edge.named_edge_triple for edge in unstable_pairs[key]}
            self.assertEqual(
                set(expected_unstable[key.named_edge_triple]),
                unstable_key_vals)

    def test_match(self):
        # TODO: Remove string or obj tests depending on which match uses.
        # # Case 1: Rename
        # current = ('source', 'target', 'type')
        # clone = ('new source', 'target', 'type')
        # self.assertEqual(1, match(current=current, clone=clone))
        # # Case 2: Same edge different otherwise
        # current = ('source', 'target', 'type')
        # clone = ('new source', 'new target', 'type')
        # self.assertEqual(0, match(current=current, clone=clone))
        # # Case 3: Edge of current longer than edge of clone
        # current = ('source', 'target', 'owner')
        # clone = ('new source', 'new target', 'type')
        # self.assertEqual(-1, match(current=current, clone=clone))
        # # Case 4: Edge of current shorter than edge of clone
        # current = ('source', 'target', 'type')
        # clone = ('new source', 'new target', 'memberEnd')
        # self.assertEqual(-2, match(current=current, clone=clone))
        car = Vertex(name='Car')
        engine = Vertex(name='engine')
        wheel = Vertex(name='wheel')

        # need a test for when I implement the 'edge type equivalence'
        # This would address a case: Suppose the edge attribtue 'type'
        # was in the edge set of Original_edge_attributes but 'type'not
        # in the edge set of Change_edge_attribtues and instead 'new type' was
        # there. Then I would want a way to say type -> new type.
        og_edge = DiEdge(source=car, target=engine,
                         edge_attribute='owner')

        # case: different target
        match_edge = DiEdge(source=car, target=wheel,
                            edge_attribute='owner')
        match_val = match(current=og_edge, clone=match_edge)
        self.assertEqual(1, match_val)

        # case: different source
        match_edge2 = DiEdge(source=wheel, target=engine,
                             edge_attribute='owner')
        match_val = match(current=og_edge, clone=match_edge2)
        self.assertEqual(1, match_val)

        # case: same edge type different otherwise
        match_edge3 = DiEdge(source=wheel, target=car,
                             edge_attribute='owner')
        match_val = match(current=og_edge, clone=match_edge3)
        self.assertEqual(0, match_val)

        # case: original edge type longer than change
        short_edge = DiEdge(source=car, target=engine, edge_attribute='type')
        match_val = match(current=og_edge, clone=short_edge)
        self.assertEqual(-1, match_val)

        # case: original edge type shorter than chagne
        long_edge = DiEdge(source=car, target=engine,
                           edge_attribute='memberEnd')
        match_val = match(current=og_edge, clone=long_edge)
        self.assertEqual(-2, match_val)

    def test_recast_new_names_as_old(self):
        base_inputs = [('s1', 't1', 'type'),
                       ('s12', 't12', 'memberEnd'),
                       ('song', 'tiger', 'blue'), ]

        ancestor = [('as1', 't1', 'type'),
                    ('s12', 'at12', 'memberEnd'), ('b', 'c', 'orange')]

        base_edges = []
        base_dict = {}
        ancestor_edges = []
        ancestor_dict = {}

        for edge_tuple in base_inputs:
            source = Vertex(name=edge_tuple[0])
            target = Vertex(name=edge_tuple[1])
            edge = DiEdge(source=source, target=target,
                          edge_attribute=edge_tuple[2])
            base_dict[edge_tuple] = edge
            base_edges.append(edge)

        for edge_tuple in ancestor:
            source = Vertex(name=edge_tuple[0])
            target = Vertex(name=edge_tuple[1])
            edge = DiEdge(source=source, target=target,
                          edge_attribute=edge_tuple[2])
            ancestor_dict[edge_tuple] = edge
            ancestor_edges.append(edge)

    def test_associate_node_ids(self):
        node_id_dict = {'Element Name': ['Car', 'engine', 'orange'],
                        'ID': [1, 2, 3]}
        df_ids = pd.DataFrame(data=node_id_dict)
        df_ids.set_index(df_ids.columns[0], inplace=True)
        translator = MDTranslator()
        nodes = ['Car', 'engine', 'orange', 'green']
        nodes_to_add = associate_node_ids(nodes=nodes, attr_df=df_ids,
                                          uml_id_dict=translator.get_uml_id)
        expected_node_info = [('Car', {'ID': 1}), ('engine', {'ID': 2}),
                              ('orange', {'ID': 3}),
                              ('green', {'ID': 'new_0'})]
        for count, node_tup in enumerate(nodes_to_add):
            self.assertTupleEqual(expected_node_info[count], node_tup)

    def test_get_setting_node_name_from_df(self):
        data_dict = {
            'component': ['car', 'wheel', 'engine'],
            'Atomic Thing': ['Car', 'Wheel', 'Car'],
            'edge attribute': ['owner', 'owner', 'owner'],
            'Notes': ['little car to big Car',
                      6,
                      2]
        }
        df = pd.DataFrame(data=data_dict)
        setting_node = get_setting_node_name_from_df(df=df,
                                                     column='Atomic Thing',
                                                     node='wheel')

        self.assertListEqual(['Wheel'], setting_node)

    def test_to_excel_df(self):
        og_edge = DiEdge(source=Vertex(name='green'),
                         target=Vertex(name='apple'),
                         edge_attribute='fruit')
        change_edge = DiEdge(source=Vertex(name='gala'),
                             target=Vertex(name='apple'),
                             edge_attribute='fruit')
        added_edge = DiEdge(source=Vertex(name='blueberry'),
                            target=Vertex(name='berry'),
                            edge_attribute='bush')
        deleted_edge = DiEdge(source=Vertex(name='yellow'),
                              target=Vertex(name='delicious'),
                              edge_attribute='apple')
        unstable_key = DiEdge(source=Vertex(name='tomato'),
                              target=Vertex(name='fruit'),
                              edge_attribute='fruit')
        unstable_one = DiEdge(source=Vertex(name='tomato'),
                              target=Vertex(name='vegetable'),
                              edge_attribute='fruit')
        unstable_two = DiEdge(source=Vertex(name='tomahto'),
                              target=Vertex(name='fruit'),
                              edge_attribute='fruit')

        fake_datas = {'0-1': {'Changes': {'Added': [added_edge],
                                          'Deleted': [deleted_edge],
                                          og_edge: [change_edge], },
                              'Unstable Pairs': {unstable_key: [
                                  unstable_one,
                                  unstable_two]}}}

        input_data = {}
        inner_dict = fake_datas['0-1']
        input_data.update(inner_dict['Changes'])
        input_data.update(inner_dict['Unstable Pairs'])
        str_keys = ['Edit 1', 'Edit 2', 'Added', 'Deleted']

        expected_data = {'Edit 1': [('green', 'apple', 'fruit'),
                                    ('tomato', 'fruit', 'fruit'),
                                    ('tomato', 'fruit', 'fruit')],
                         'Edit 2': [('gala', 'apple', 'fruit'),
                                    ('tomato', 'vegetable', 'fruit'),
                                    ('tomahto', 'fruit', 'fruit')],
                         'Added': [('blueberry', 'berry', 'bush')],
                         'Deleted': [('yellow', 'delicious', 'apple')]}
        expected_df = pd.DataFrame(data=dict([
            (k, pd.Series(v)) for k, v in expected_data.items()]))

        excel_data = to_excel_df(data_dict=input_data, column_keys=str_keys)
        self.assertDictEqual(expected_data, excel_data)

        excel_df = pd.DataFrame(data=dict([
            (k, pd.Series(v)) for k, v in excel_data.items()]))
        self.assertTrue(expected_df.equals(excel_df))

    def test_get_new_column_name(self):
        og_dict = {'Composite Thing': ['Car', 'Car',
                                       'Wheel', 'Engine'],
                   'component': ['engine', 'rear driver',
                                 'hub', 'drive output'],
                   'Atomic Thing': ['Engine', 'Wheel',
                                    'Hub', 'Drive Output']}
        original_df = pd.DataFrame(data=og_dict)
        rename_dict = {'old name': ['Car'],
                       'changed name': ['Subaru']}
        rename_df = pd.DataFrame(data=rename_dict)

        new_name_col = get_new_column_name(
            original_df=original_df,
            rename_df=rename_df)
        self.assertEqual('changed name', new_name_col)

    def test_replace_new_with_old_name(self):
        change_dict = {'Composite Thing': ['Subaru', 'Subaru',
                                           'Wheel', 'Engine'],
                       'component': ['engine', 'rear driver',
                                     'hub', 'drive output'],
                       'Atomic Thing': ['Engine', 'Wheel',
                                        'Hub', 'Drive Output']}
        change_df = pd.DataFrame(data=change_dict)
        rename_dict = {'old name': ['Car'],
                       'changed name': ['Subaru']}
        rename_df = pd.DataFrame(data=rename_dict)
        new_name = 'changed name'

        recast_df = replace_new_with_old_name(changed_df=change_df,
                                              rename_df=rename_df,
                                              new_name=new_name)
        og_dict = {'Composite Thing': ['Car', 'Car',
                                       'Wheel', 'Engine'],
                   'component': ['engine', 'rear driver',
                                 'hub', 'drive output'],
                   'Atomic Thing': ['Engine', 'Wheel',
                                    'Hub', 'Drive Output']}
        og_df = pd.DataFrame(data=og_dict)

        self.assertTrue(og_df.equals(recast_df))

    def test_new_as_old(self):
        ancestor = [('as1', 't1', 'type'),
                    ('s12', 'at12', 'memberEnd'), ('b', 'c', 'orange')]
        ancestor_edges = []
        ancestor_dict = {}
        for edge_tuple in ancestor:
            source = Vertex(name=edge_tuple[0])
            target = Vertex(name=edge_tuple[1])
            edge = DiEdge(source=source, target=target,
                          edge_attribute=edge_tuple[2])
            ancestor_dict[edge_tuple] = edge
            ancestor_edges.append(edge)

        expect_out_d = {('s1', 't1', 'type'): ancestor_dict[ancestor[0]],
                        ('s12', 't12', 'memberEnd'): ancestor_dict[
                            ancestor[1]],
                        ('b', 'cyborg', 'orange'): ancestor_dict[ancestor[2]],
                        }

        new_keys = {'at12': 't12',
                    'c': 'cyborg',
                    'as1': 's1', }

        output = new_as_old(main_dict=ancestor_dict,
                            new_keys=new_keys)

        expect_reverse = {'t12': 'at12',
                          'cyborg': 'c',
                          's1': 'as1', }
        # check that all of the vertex names got changed
        vert_names = {key: key
                      for key in expect_out_d.keys()}
        vert_fn_names = {key: output[0][key].named_edge_triple
                         for key in output[0]}

        self.assertDictEqual(expect_out_d, output[0])
        self.assertDictEqual(expect_reverse, output[1])
        self.assertDictEqual(vert_names, vert_fn_names)

        # Can I take the output and get the input?
        new_out = new_as_old(main_dict=output[0], new_keys=output[1])

        v_names = {key: key
                   for key in ancestor_dict.keys()}
        v_fn_names = {key: new_out[0][key].named_edge_triple
                      for key in new_out[0]}

        self.assertDictEqual(ancestor_dict, new_out[0])
        self.assertDictEqual(new_keys, new_out[1])
        self.assertDictEqual(v_names, v_fn_names)

    def test_to_nto_rename_dict(self):
        renm_d = {
            'change name': ['Big Cylinder', 'Locking Nut'],
            'previous name': ['Cylinder', 'Lug Nut'],
        }
        new_to_old, rename_changes = to_nto_rename_dict(new_name='change name',
                                                        new_name_dict=renm_d)
        self.assertDictEqual({'Big Cylinder': 'Cylinder',
                              'Locking Nut': 'Lug Nut'}, new_to_old)

        self.assertDictEqual({'Rename change name': ['Big Cylinder',
                                                     'Locking Nut'],
                              'Rename previous name': ['Cylinder', 'Lug Nut']},
                             rename_changes)

    def tearDown(self):
        pass


if __name__ == '__main__':
    unittest.main()
