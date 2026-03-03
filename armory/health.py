from __future__ import annotations

from .constants import CLASS_BASE_HP_80
from .models import CharacterProfile


def estimate_max_hp(profile: CharacterProfile) -> int:
    class_key = profile.klass.upper()
    if class_key not in CLASS_BASE_HP_80:
        raise ValueError(f"No base HP data mapped for class: {profile.klass}")

    base_hp = float(CLASS_BASE_HP_80[class_key])

    # Tauren racial Endurance in WotLK: +5% base health.
    if profile.race.strip().lower() == "tauren":
        base_hp *= 1.05

    stamina = float(profile.stamina)
    base_stamina = min(20.0, stamina)
    extra_stamina = stamina - base_stamina
    hp_from_stamina = base_stamina + (extra_stamina * 10.0)

    return int(base_hp + hp_from_stamina)
