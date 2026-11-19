"""Player settings applied to the running game (sound, text, scrolling, speed)."""
import time
from dq456_pc.persistence import settings as RG
from dq456_pc.window.constants import SFX_PREVIEW, SFX_BUTTON


class OptionsMixin:
    """Player settings applied to the running game (sound, text, scrolling, speed)."""

    def set_sound(self, yes):
        if bool(yes) != self.sound.active:
            self.sound.toggle()
            if self.sound.active and self.engine.state.music is not None: self.sound.play_bgm(self.engine.state.music)

    # ---- sound by category (Esc menu > "Sound"): see sound.py (CATEGORIES, Mixer)
    def apply_mix(self, initial=False):
        """Volumes and switches of the settings -> sound.mix, immediately for the sounds already playing. At startup, the music and sound effect volumes are those from the command line (Sound already has them)."""
        R = self.reg; vol = dict(jingles=R['jingle_volume'], interface=R['interface_volume'])
        if not initial: vol.update(music=R['music_volume'], effects=R['sfx_volume'])
        self.sound.set_mix(general=R['master_volume'], volumes=vol, active_flags=dict(music=R['music_enabled'], jingles=R['jingles_enabled'], effects=R['sfx_enabled'], interface=R['interface_enabled']))

    def preview_sound(self, category):
        """Setting a volume on the "Sound" page: a test sound effect of the category (at most one per quarter second); the music, for its part, is heard throughout the page (Sound.listen)."""
        t = time.time()
        if t - self._t_preview < 0.25: return
        self._t_preview = t
        if category in ('general', 'effects') and self.sound.mix.gain('effects') > 0.0: self.sound.play_sfx(SFX_PREVIEW)
        elif category in ('general', 'interface'): self.sound.play_sfx(SFX_BUTTON)

    # ---- dialogue text speed and battle message scrolling (Esc menu > "Display" > "Text scrolling")
    def apply_text(self): self.engine.text_speed = float(self.reg['text_speed'])

    def apply_all(self):
        """The settings of another game were just put in place (game_rules: each game has its own): everything that does not read them live (rules, sound, text and battle speeds,
        sprites, on-screen information); the display, the interface and the keys read them at each frame."""
        self.apply_game(); self.apply_mix(); self.apply_text(); self.apply_scroll()
        if hasattr(self, 'set_mode'): self.set_mode(self.reg['sprite_mode'])
        self.set_sound(self.reg['sound']); self.helptext = bool(self.reg['info'])

    def apply_game(self):
        """"Difficulty" page of the Esc menu (formerly "Extras", "Modifiers", "Changes", formerly "Game"), "Difficulty" category: options that change a game rule (HP and MP restored on level up, at the end of a battle; experience and gold gained, damage taken by the party and by enemies; random encounters and their rate)."""
        self.engine.level_heal = bool(self.reg['level_up_heal'])
        self.engine.battle_heal = bool(self.reg['battle_end_heal'])
        self.engine.exp_rate = float(self.reg['exp_rate']); self.engine.gold_rate = float(self.reg['gold_rate']); self.engine.casino_rate = float(self.reg['casino_rate'])
        self.engine.party_damage_rate = float(self.reg['party_damage_rate']); self.engine.enemy_damage_rate = float(self.reg['enemy_damage_rate'])
        self.engine.encounter_rate = float(self.reg['encounter_rate']) if self.reg['random_encounters'] else 0.0

    def apply_scroll(self):
        """"Battle speed" -> OptionStatus.battleSpeed imposed on the engine: 4 (manual messages) in "Manual", 0 (the game's shortest wait, 12 frames) otherwise (RG.scroll_code); "Fast" and "Tres rapide" speed up the clock, and therefore the wait too."""
        self.engine.impose_scroll_mode(RG.scroll_code(self.reg['battle_speed']))

    def _adopt_scroll(self, code):
        """The game itself changes the message speed (original Settings window): 4 -> "Manual", any other value -> leaves "Manual" (RG.speed_after_game_code)."""
        self.reg['battle_speed'] = RG.speed_after_game_code(code, self.reg['battle_speed'])
        self.apply_scroll()
