"""Reading of the savestates recorded BEFORE the keys of their dictionaries were in English (stage 3): the State and Interface objects, the header, the
`python` and `viewer` dictionaries are brought back to the current names, nothing is lost, the new name wins when both are present, and a state in the current form is not touched.

python3 tests/test_legacy_names.py
"""
import copy, os, pickle, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dq456_pc.core import engine as ENGINE, legacy_state as LS
from dq456_pc.persistence import savestates as SS


def old_state_dict():
    """__dict__ of a State as the version pickled it (French keys inside the dictionaries; the attributes themselves are already English)."""
    d = dict(ENGINE.State().__dict__)
    d['fade'] = {'a': 0.5, 'fin': 1.0, 'pas': 0.1, 'n': 4, 'col': (0.0, 0.0, 0.0), 'noir': 7, 'combat': True}
    d['background_fade'] = {'a': 0.0, 'fin': 0.0, 'pas': 0.0, 'n': 0, 'col': (0.0, 0.0, 0.0), 'noir': 0, 'combat': False}
    d['effect'] = {'n': 3, 'duree': 57}
    d['screen_effect'] = {'n': 2, 'duree': 64, 'images': 64, 'genre': 'lampe', 'inverse': False, 'matin': True, 'noir': True, 'fondu': True}
    d['field'] = {'x0': 0, 'y0': 0, 'cols': 2, 'tuiles': [1, 2], 'cam': None}
    d['sprites'] = {1: {'id': 3, 'pos': None, 'col': (1, 1, 1, 1), 'pose': 0, 'dir': 0, 'vis': True, 'ech': 1.5, 'cree': 5, 'dort': True, 'dort_rot': (0.0, 0), 'ombre': False,
                        'ombre_sep': True, 'ombre_pos': (1.0, 2.0, 3.0), 'ombre_a': 0.5, 'ombre_champ': (4.0, 5.0, 6.0)}}
    d['symbols'] = {2: {'genre': 7, 'x': 1.0, 'y': 2.0, 'alpha': 1.0, 'vis': False}}
    d['fbx'] = {0: {'id': 1018, 'vis': True, 'pos': (0, 0, 0), 'rot': (0, 0, 0), 'scl': (1, 1, 1), 'col': (1, 1, 1, 1), 'anim': []}}
    d['mesh_state'] = {1: {'shader': 1, 'vis': False, 'col': (1.0, 1.0, 1.0), 'off': (0.0, 0.0)}}
    d['object_cmds'] = [('carte',), ('anim', 1, 2)]
    return d


NEW_STATE = {
    'fade': {'a': 0.5, 'end': 1.0, 'step': 0.1, 'n': 4, 'col': (0.0, 0.0, 0.0), 'black': 7, 'battle': True},
    'effect': {'n': 3, 'duration': 57},
    'screen_effect': {'n': 2, 'duration': 64, 'frames': 64, 'kind': 'lamp', 'inverse': False, 'morning': True, 'black': True, 'fade_in': True},
    'field': {'x0': 0, 'y0': 0, 'cols': 2, 'tiles': [1, 2], 'cam': None},
    'sprites': {1: {'id': 3, 'pos': None, 'col': (1, 1, 1, 1), 'pose': 0, 'dir': 0, 'visible': True, 'scale': 1.5, 'created': 5, 'sleeping': True, 'sleeping_rot': (0.0, 0), 'shadow': False,
                    'shadow_separate': True, 'shadow_pos': (1.0, 2.0, 3.0), 'shadow_alpha': 0.5, 'shadow_field': (4.0, 5.0, 6.0)}},
    'symbols': {2: {'kind': 7, 'x': 1.0, 'y': 2.0, 'alpha': 1.0, 'visible': False}},
    'fbx': {0: {'id': 1018, 'visible': True, 'pos': (0, 0, 0), 'rot': (0, 0, 0), 'scl': (1, 1, 1), 'col': (1, 1, 1, 1), 'anim': []}},
    'mesh_state': {1: {'shader': 1, 'visible': False, 'col': (1.0, 1.0, 1.0), 'off': (0.0, 0.0)}},
    'object_cmds': [('map',), ('anim', 1, 2)],
}


def clock(**k): return dict(dict(delai=0, rdelai=0, rep=-1, fin=84, temps=3, fini=False), **k)


class StateKeys(unittest.TestCase):
    def test_state_with_french_keys(self):
        s = ENGINE.State.__new__(ENGINE.State); s.__setstate__(old_state_dict())
        for name, wanted in NEW_STATE.items(): self.assertEqual(getattr(s, name), wanted, name)
        self.assertEqual(s.background_fade['battle'], False); self.assertEqual(s.background_fade['end'], 0.0)

    def test_state_in_the_current_form_is_unchanged(self):
        d = old_state_dict(); d.update(copy.deepcopy(NEW_STATE)); d['background_fade'] = ENGINE.State()._fade_plane()
        s = ENGINE.State.__new__(ENGINE.State); s.__setstate__(copy.deepcopy(d))
        for name, wanted in NEW_STATE.items(): self.assertEqual(getattr(s, name), wanted, name)

    def test_pickle_of_an_old_state_through_the_whitelist(self):
        old = ENGINE.State.__new__(ENGINE.State); old.__dict__.update(old_state_dict())
        r = SS._load(pickle.dumps(old, protocol=3))
        for name, wanted in NEW_STATE.items(): self.assertEqual(getattr(r, name), wanted, name)

    def test_the_new_name_wins(self):
        d = old_state_dict(); d['sprites'][1]['visible'] = False
        s = ENGINE.State.__new__(ENGINE.State); s.__setstate__(d)
        self.assertFalse(s.sprites[1]['visible']); self.assertNotIn('vis', s.sprites[1])


class InterfaceKeys(unittest.TestCase):
    def test_interface_with_french_keys(self):
        ui = ENGINE.Interface.__new__(ENGINE.Interface)
        old = {'f': {20: {'cases': {(0, 0): 'x'}, 'vis': True, 'cur': 2, 'ordre': 4, 'indic': {1: 5}, 'type': 31, 'act': True, 'req': False, 'draw': True, 'force': False, 'ign': False,
                          'sv': True, 'inp': True, 'entree': True, 'ferme': False, 'ints': {}, 'listes': {3: [1]}, 'suite': None, 'dispo': 2, 'att': (1, 'nom'), 'n_codes': {},
                          'grille': (2, 3, 6), 'plaq': {0: {'code': 2, 'nom': 'Gluant', 'prm': [1, 2]}, 1: {'code': 1}}, 'dgt': False}},
               'msg': {'type': 1, 'y': 0, 'feed': True, 'shake': 0, 'qui': 'Alena', 'qui_att': True}, 'waiting': {}, 'order': 4, 'damage': [], 'system': [], 'obs': None}
        ui.__setstate__(old)
        f = ui.f[20]
        self.assertEqual((f['cells'], f['visible'], f['order'], f['indicators'], f['input'], f['closed'], f['lists'], f['next_list'], f['layout'], f['grid']),
                         ({(0, 0): 'x'}, True, 4, {1: 5}, True, False, {3: [1]}, None, 2, (2, 3, 6)))
        self.assertEqual((f['pending'], f['damage_pending']), ((1, 'name'), False))
        self.assertEqual(f['plates'], {0: {'code': 2, 'name': 'Gluant', 'params': [1, 2]}, 1: {'code': 1}})
        self.assertEqual((ui.msg['speaker'], ui.msg['speaker_pending']), ('Alena', True))
        self.assertFalse({'cases', 'vis', 'ordre', 'indic', 'entree', 'ferme', 'listes', 'suite', 'dispo', 'att', 'grille', 'plaq', 'dgt'} & set(f))

    def test_a_window_without_plates_or_pending(self):
        ui = ENGINE.Interface.__new__(ENGINE.Interface); ui.__setstate__({'f': {5: {'vis': False, 'att': None, 'plaq': {}}}, 'msg': None})
        self.assertEqual(ui.f[5], {'visible': False, 'pending': None, 'plates': {}})


class FileKeys(unittest.TestCase):
    def test_header(self):
        self.assertEqual(LS.renamed_info({'lieu': 'settings.battle', 'carte': 'ev01', 'partie': 12, 'images': 99, 'date': 'd', 'version': 1}),
                         {'location': 'settings.battle', 'map': 'ev01', 'part': 12, 'frames': 99, 'date': 'd', 'version': 1})

    def test_header_read_from_an_old_file(self):
        f = os.path.join(tempfile.mkdtemp(prefix='legacy_'), 'e.dqs')
        SS.write(f, {'version': SS.VERSION}, {'lieu': 'settings.world_map', 'carte': 'mak1f1', 'partie': 14, 'images': 7})
        info, _ = SS.info(f)
        self.assertEqual((info['location'], info['map'], info['part'], info['frames']), ('settings.world_map', 'mak1f1', 14, 7))

    def test_outer_and_python_dictionaries(self):
        self.assertEqual(LS.renamed_file({'fichiers': {1: 2}, 'heap': b''}), {'files': {1: 2}, 'heap': b''})
        p = LS.renamed_python({'etat': 'S', 'ui': 'U', 'images': 12, 'grille': 'G', 'grille_img': 3, 'anims': []})
        self.assertEqual(p, {'state': 'S', 'ui': 'U', 'frames': 12, 'grid': 'G', 'grid_frame': 3, 'anims': []})

    def test_viewer(self):
        old = {'objets_etat': {4: {'mdl': 7, 'off': False, 'alpha': 31, 'pos': None, 'rot': None, 'temps': 12, 'tmot': 3, 'tseq': 9, 'fini': False,
                                  'mot': {'delai': 1, 'rdelai': 2, 'fin': 800, 'repeat': -1, 'flag': 0, 'keys': [], 'nkey': 0}, 'seq': None}},
               'objets_auto': {4: {'seq': {'delai': 0, 'rdelai': 0, 'fin': 84, 'repeat': 0, 'keys': []}, 'mot': None, 'hs': clock(), 'hm': None}},
               'objets_evt': (3, [1, 2]), 'objets_sra': {0: clock(rep=2)}, 'carte_nom': 'x', 'motif_n': 1, 'motif_acc': [0], 'musique': None, 'palettes': {1: 2}}
        v = LS.renamed_viewer(copy.deepcopy(old))
        self.assertEqual(set(v), {'object_states', 'auto_objects', 'event_objects', 'sra_clocks', 'map_name', 'pattern_n', 'acc_pattern', 'music', 'palettes'})
        st = v['object_states'][4]
        self.assertEqual((st['model'], st['time'], st['motion_time'], st['sequence_time'], st['finished']), (7, 12, 3, 9, False))
        self.assertEqual(st['motion'], {'delay': 1, 'loop_delay': 2, 'end': 800, 'repeat': -1, 'flag': 0, 'keys': [], 'nkey': 0}); self.assertIsNone(st['sequence'])
        a = v['auto_objects'][4]
        self.assertEqual(a['sequence_clock'], {'delay': 0, 'loop_delay': 0, 'loops': -1, 'end': 84, 'time': 3, 'finished': False}); self.assertIsNone(a['motion_clock'])
        self.assertEqual(a['sequence']['end'], 84)
        self.assertEqual(v['sra_clocks'][0]['loops'], 2); self.assertEqual(v['event_objects'], (3, [1, 2]))

    def test_very_old_single_clock_format(self):
        v = LS.renamed_viewer({'objets_auto': {1: {'seq': None, 'mot': {'delai': 0, 'rdelai': 0, 'repeat': -1, 'fin': 800, 'keys': []}, 'delai': 5, 'rdelai': 6, 'rep': 2, 'fin': 90, 'temps': 1, 'fini': False}}})
        a = v['auto_objects'][1]
        self.assertEqual((a['delay'], a['loop_delay'], a['loops'], a['end'], a['time'], a['finished']), (5, 6, 2, 90, 1, False))

    def test_anything_else_is_left_alone(self):
        self.assertIsNone(LS.renamed_viewer(None)); self.assertEqual(LS.renamed_viewer({'palettes': 1}), {'palettes': 1})
        self.assertEqual(LS.renamed_python({'state': 1, 'etat': 2}), {'state': 1})


class HistoryFile(unittest.TestCase):
    OLD = {'version': 2, 'suivant': 9, 'favoris': [
        {'k': 'd', 'id': 3, 't': 12345, 'nom': 'Alena', 'texte': 'Bonjour.'},
        {'k': 'd', 'id': 4, 't': 12400, 'nom': None, 'mid': 802199, 's': 1, 'v': {'[NONE 1,0]': 'Hero'}},
        {'k': 'c', 'id': 5, 't': 1, 'ennemis': [{'nom': 'Gluant', 'total': 3, 'vaincus': 2, 'fuis': 1, 'disparus': 0}], 'or': 3, 'xp': 4, 'issue': 'fuite', 'objets': [{'nom': 'Herbe médicinale'}]},
        {'k': 'c', 'id': 6, 't': 2, 'ennemis': [{'nom': 'Golem', 'total': 1, 'vaincus': 1}], 'or': 0, 'xp': 0, 'issue': 'victoire'},
        {'k': 'c', 'id': 7, 't': 3, 'ennemis': [{'nom': 'Golem', 'total': 1, 'vaincus': 0}], 'or': 0, 'xp': 0, 'issue': 'defaite', 'objets': []}]}

    def test_version_2_file_is_read_then_rewritten_in_english(self):
        import json
        from dq456_pc.core import history as HI
        f = os.path.join(tempfile.mkdtemp(prefix='legacy_hist_'), 'history.json')
        with open(f, 'w', encoding='utf-8') as fh: json.dump(self.OLD, fh)
        h = HI.History(f); h.set_adventure('0123456789ab')                                                  # (the common favorites go to the first adventure)
        self.assertIsNone(h.error); self.assertEqual([e.fav for e in h.favorites], [3, 4, 5, 6, 7]); self.assertEqual(h.next_id, 9)
        d, linked, b1, b2, b3 = h.favorites
        self.assertEqual((d.name_str, d.text), ('Alena', 'Bonjour.')); self.assertEqual((linked.mid, linked.seg, linked.val), (802199, 1, {'[NONE 1,0]': 'Hero'}))
        self.assertEqual((b1.outcome, b1.gold, b1.xp), ('escape', 3, 4))
        self.assertEqual(b1.enemies, [{'name': 'Gluant', 'total': 3, 'defeated': 2, 'fled': 1, 'vanished': 0}]); self.assertEqual(b1.objects, [{'name': 'Herbe médicinale'}])
        self.assertEqual((b2.outcome, b3.outcome), ('victory', 'defeat'))
        h.store(force=True)
        with open(h.path, encoding='utf-8') as fh: saved = json.load(fh)
        self.assertEqual((saved['version'], saved['next']), (3, 9)); self.assertEqual(len(saved['favorites']), 5)
        text = json.dumps(saved)
        for old in ('"nom"', '"texte"', '"ennemis"', '"vaincus"', '"fuis"', '"issue"', '"objets"', '"suivant"', '"favoris"', 'victoire', 'fuite', 'defaite'): self.assertNotIn(old, text)
        h2 = HI.History(f); h2.set_adventure('0123456789ab'); self.assertEqual([e.to_dict() for e in h2.favorites], [e.to_dict() for e in h.favorites])

    def test_migration_function_alone(self):
        d = LS.renamed_history(copy.deepcopy(self.OLD))
        self.assertEqual((d['next'], len(d['favorites'])), (9, 5)); self.assertEqual(d['favorites'][2]['outcome'], 'escape'); self.assertEqual(d['favorites'][2]['enemies'][0]['fled'], 1)
        self.assertEqual(LS.renamed_history({'favoris': 'x'}), {'favorites': 'x'}); self.assertEqual(LS.renamed_history(5), 5)


if __name__ == '__main__':
    unittest.main()
