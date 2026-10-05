"""Build the mod paks.

Two paks are produced. They are ALTERNATIVES — install one, not both, since
both carry the same Game.locres and Game.locmeta:

  AstroneerDanish_P.pak                 translations + an entry in the in-game
                                        language dropdown. The normal choice.
  AstroneerDanishTranslationOnly_P.pak  translations only. Does not override
                                        LocalizationCultureOptions, so it can
                                        coexist with another language mod that
                                        patches the same asset. Needs the
                                        -culture=<code> launch option.

The _P suffix gives a pak higher mount priority than pakchunk0, so its files
shadow the base game's copies at runtime. Nothing in the game install is
modified — deleting the pak restores stock behaviour.
"""

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import culture as culture_asset
from . import locmeta, repak, translations
from .console import Failure, detail, ok, warn

CONTENT_ROOT = "Astro/Content"
LOC_ROOT = f"{CONTENT_ROOT}/Localization/Game"
LOCMETA_PATH = f"{LOC_ROOT}/Game.locmeta"
CULTURE_ASSET = f"{CONTENT_ROOT}/Globals/LocalizationCultureOptions"

# Fixed names: the README documents them and people have them installed.
FULL_PAK = "AstroneerDanish_P.pak"
TRANSLATION_ONLY_PAK = "AstroneerDanishTranslationOnly_P.pak"


@dataclass
class Result:
    progress: translations.Progress = field(default_factory=translations.Progress)
    dropped: int = 0
    paks: list = field(default_factory=list)   # (path, size) built this run
    full_built: bool = False
    installed: Path | None = None


class Builder:
    def __init__(self, repo_dir, game, culture="da", display="Dansk"):
        self.repo_dir = Path(repo_dir)
        self.game = game
        self.culture = culture
        self.display = display
        self.build_dir = self.repo_dir / "build"
        self.out_dir = self.repo_dir / "mod-output"
        self.full_pak = self.out_dir / FULL_PAK
        self.translation_only_pak = self.out_dir / TRANSLATION_ONLY_PAK

    def clean(self):
        removed = []
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir, ignore_errors=True)
            removed.append(f"{self.build_dir.name}/")
        for pak in (self.translation_only_pak, self.full_pak):
            if pak.is_file():
                pak.unlink()
                removed.append(str(pak.relative_to(self.repo_dir)))
        return f"removed {', '.join(removed)}" if removed else "nothing to remove"

    def build(self, po_path, install=False, quiet=False):
        po_path = Path(po_path)
        if not po_path.is_file():
            raise Failure(f"translation file not found: {po_path}")
        result = Result()
        result.progress = translations.progress(po_path)

        version, seed, matched = self.game.pak_format()
        if not matched and not quiet:
            warn(f"could not parse base pak info; using defaults {version} / {seed:#X}")

        # ------------------------------------------------ stage the translations
        shutil.rmtree(self.build_dir, ignore_errors=True)
        stage_loc = self.build_dir / "pak-translation-only"
        loc_dir = stage_loc / LOC_ROOT
        (loc_dir / self.culture).mkdir(parents=True)

        locres_path = loc_dir / self.culture / "Game.locres"
        _, result.dropped = translations.compile_locres(po_path, locres_path)

        # The stock Game.locmeta lists only the cultures the game shipped with,
        # and it lives at the localization-target root, not inside the culture
        # folder. Add ours so the new locres is part of the manifest.
        patched_locmeta, cultures = locmeta.add_culture(
            self.game.read(LOCMETA_PATH), self.culture
        )
        (loc_dir / "Game.locmeta").write_bytes(patched_locmeta)

        expected_locres = f"{LOC_ROOT}/{self.culture}/Game.locres"
        expected_locmeta = LOCMETA_PATH

        if not quiet:
            size = locres_path.stat().st_size / 1024
            ok(f"compiled {expected_locres} ({size:.0f}K)")
            if result.dropped:
                detail(f"dropped {result.dropped} untranslated entries with no English fallback")
            detail(f"locmeta lists {len(cultures)} cultures: {', '.join(cultures)}")

        # ------------------------------------- pak 1: translations on their own
        repak.pack(
            stage_loc, self.translation_only_pak, version, seed,
            expected=(expected_locres, expected_locmeta),
        )
        result.paks.append((self.translation_only_pak, self.translation_only_pak.stat().st_size))

        # ------------------------- pak 2: translations + the dropdown entry
        # Nothing enumerates the locres folders at runtime — the in-game
        # language list comes from the DisplayLanguageToCultureMapping map
        # inside the LocalizationCultureOptions asset, so this pak ships an
        # overriding copy with our culture appended. That override is the only
        # reason the two paks differ, and the only thing that can clash with
        # another language mod.
        uasset = self.game.try_read(f"{CULTURE_ASSET}.uasset")
        uexp = self.game.try_read(f"{CULTURE_ASSET}.uexp")
        if uasset and uexp:
            stage_full = self.build_dir / "pak-full"
            full_loc = stage_full / LOC_ROOT
            (full_loc / self.culture).mkdir(parents=True)
            shutil.copy2(locres_path, full_loc / self.culture / "Game.locres")
            shutil.copy2(loc_dir / "Game.locmeta", full_loc / "Game.locmeta")

            patched_uasset, patched_uexp, languages, delta = culture_asset.add_language(
                uasset, uexp, self.culture, self.display
            )
            globals_dir = stage_full / CULTURE_ASSET
            globals_dir.parent.mkdir(parents=True, exist_ok=True)
            globals_dir.with_suffix(".uasset").write_bytes(patched_uasset)
            globals_dir.with_suffix(".uexp").write_bytes(patched_uexp)
            if not quiet:
                if delta:
                    detail(f"dropdown: added '{self.display}' -> '{self.culture}' "
                           f"({len(languages)} languages, .uexp +{delta} bytes)")
                else:
                    detail(f"dropdown already lists '{self.culture}'")

            repak.pack(
                stage_full, self.full_pak, version, seed,
                expected=(expected_locres, expected_locmeta,
                          f"{CULTURE_ASSET}.uasset", f"{CULTURE_ASSET}.uexp"),
            )
            result.paks.append((self.full_pak, self.full_pak.stat().st_size))
            result.full_built = True
        else:
            # Never leave a stale full pak beside a freshly built one.
            self.full_pak.unlink(missing_ok=True)
            warn(f"skipped {self.full_pak.name} — it embeds an override of the game's own")
            warn("LocalizationCultureOptions asset, which could not be read from the base pak.")

        if install:
            result.installed = self.install(result.full_built)
        return result

    def install(self, full_built):
        dest_dir = self.game.paks_dir
        if not dest_dir.is_dir():
            raise Failure(f"game Paks directory not found: {dest_dir}")
        chosen = self.full_pak if full_built else self.translation_only_pak
        # The two paks overlap, so clear the other one rather than leaving the
        # game to pick between two copies of Game.locres.
        for other in (self.full_pak, self.translation_only_pak):
            if other == chosen:
                continue
            stale = dest_dir / other.name
            if stale.is_file():
                stale.unlink()
                ok(f"removed previously installed {other.name}")
        shutil.copy2(chosen, dest_dir / chosen.name)
        return dest_dir / chosen.name
