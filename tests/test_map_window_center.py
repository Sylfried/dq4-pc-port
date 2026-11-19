"""Map overviews (town and world) centered on the screen by default, their two buttons (map mode, back) just right of the map's bottom right corner. All the map windows (town plan,
shop list, world maps) move by the same shift, the one that centers the reference frame (WorldLargeMap's layout): switching views moves nothing they share.

The phone showed the map at the top of its portrait screen and the buttons at the bottom right of that screen. On PC the map goes to the middle of the window and the buttons beside it;
the interface editor's settings (size, shift) apply from that place.

  python3 tests/test_map_window_center.py
"""
import os, sys, types, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
try:
    from dq456_pc.window import menu_display as MD
except Exception as ex:          # (pyglet needs a display library)
    MD = None; WHY = str(ex)

MAP_BOX = (-227.0, 58.5, 227.0, 402.0)          # the game's layout (x0, z0, x1, z1), the same for the town and the world map
BUTTON_BOX = (149.0, -402.0, 227.0, -266.0)


class Box:
    def __init__(self, b): self.b = b
    def menu_border(self, *a): return self.b
    def center_visible(self): return ((self.b[0] + self.b[2]) / 2.0, (self.b[1] + self.b[3]) / 2.0)


def window(w=1920, h=1080, ui_x=None):
    """Stand-in of the game window: frame of reference of the interface column at ui_x (center of the screen by default), 1.35 pixels per unit, the town map as preview."""
    g = types.SimpleNamespace(width=w, height=h)
    g._ui_custom = lambda mode, s, v: ((w / 2.0 if ui_x is None else ui_x) + v[1] * w, h / 2.0 + v[2] * h, s * v[0])
    g._preview_window = lambda name: Box(MAP_BOX)
    g._map_anchor = types.MethodType(MD.MenusMixin._map_anchor, g); g._map_reference = types.MethodType(MD.MenusMixin._map_reference, g)
    return g, types.MethodType(MD.MenusMixin._ui_place, g)


@unittest.skipIf(MD is None, 'window modules need pyglet')
class Placement(unittest.TestCase):
    def screen_box(self, place, name, box, v=(1.0, 0.0, 0.0)):
        cx, cy, s = place(name, Box(box), 'center', 1.35, v)
        return cx + box[0] * s, cy + box[1] * s, cx + box[2] * s, cy + box[3] * s

    def test_map_centered(self):
        for name in ('CityMap', 'WorldLargeMap'):
            g, place = window()
            x0, y0, x1, y1 = self.screen_box(place, name, MAP_BOX)
            self.assertAlmostEqual((x0 + x1) / 2, 960.0); self.assertAlmostEqual((y0 + y1) / 2, 540.0)

    def test_centered_on_the_screen_whatever_the_column(self):
        g, place = window(ui_x=1920 - 225 * 1.35)          # interface column on the right
        x0, y0, x1, y1 = self.screen_box(place, 'CityMap', MAP_BOX); self.assertAlmostEqual((x0 + x1) / 2, 960.0)

    def test_buttons_just_right_of_the_bottom_right_corner(self):
        g, place = window()
        mx0, my0, mx1, my1 = self.screen_box(place, 'CityMap', MAP_BOX)
        bx0, by0, bx1, by1 = self.screen_box(place, 'MapButton', BUTTON_BOX)
        self.assertAlmostEqual(by0, my0, msg='bottoms aligned'); self.assertAlmostEqual(bx0 - mx1, MD.MAP_BUTTON_GAP * 1.35, msg='just right of the map')

    def test_views_keep_their_places(self):
        """The shop list (z 56.5 to 402) and a town plan with its tab (58.5 to 424) are not centered each on itself: they keep the game's places relative to the reference frame."""
        g, place = window()
        ref = self.screen_box(place, 'WorldLargeMap', MAP_BOX)
        shops = self.screen_box(place, 'ShopMap', (-227.0, 56.5, 227.0, 402.0)); town = self.screen_box(place, 'CityMap', (-227.0, 58.5, 227.0, 424.0))
        self.assertAlmostEqual(shops[1], ref[1] - 2.0 * 1.35); self.assertAlmostEqual(shops[3], ref[3])
        self.assertAlmostEqual(town[1], ref[1]); self.assertAlmostEqual(town[3], ref[3] + 22.0 * 1.35)

    def test_no_room_on_the_right_buttons_under_the_map(self):
        g, place = window(w=620, h=1100)                     # portrait: the map takes the whole width
        mx0, my0, mx1, my1 = self.screen_box(place, 'CityMap', MAP_BOX)
        bx0, by0, bx1, by1 = self.screen_box(place, 'MapButton', BUTTON_BOX)
        self.assertAlmostEqual(bx1, mx1, msg='right edges aligned'); self.assertLess(by1, my0, 'under the map'); self.assertLessEqual(bx1, 620)

    def test_player_settings_apply_from_there(self):
        g, place = window()
        x0, y0, x1, y1 = self.screen_box(place, 'CityMap', MAP_BOX, v=(1.0, 0.1, -0.05))
        self.assertAlmostEqual((x0 + x1) / 2, 960.0 + 192.0); self.assertAlmostEqual((y0 + y1) / 2, 540.0 - 54.0)
        x0, y0, x1, y1 = self.screen_box(place, 'CityMap', MAP_BOX, v=(1.5, 0.0, 0.0))
        self.assertAlmostEqual((x0 + x1) / 2, 960.0); self.assertAlmostEqual((y0 + y1) / 2, 540.0, msg='resized around its center')

    def test_other_windows_untouched(self):
        g, place = window(); self.assertEqual(place('ItemList', Box(MAP_BOX), 'center', 1.35, (1.0, 0.0, 0.0)), (960.0, 540.0, 1.35))


if __name__ == '__main__':
    unittest.main()
