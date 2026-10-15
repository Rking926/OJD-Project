"""Module téléphone : métadonnées d'un numéro via la lib `phonenumbers`.

100% hors-ligne, sans clé API, sans binaire externe (remplace phoneinfoga,
plus fiable à installer). Donne : validité, pays, opérateur probable, type de
ligne (mobile/fixe/VoIP), fuseaux horaires et formats normalisés.

Le numéro doit idéalement être au format international (ex: +33612345678).
"""
from __future__ import annotations

from .base import InputType, ModuleResult, ModuleResultEntity, OsintModule

_TYPE_LABELS = {
    0: "fixe", 1: "mobile", 2: "fixe ou mobile", 3: "numéro spécial",
    4: "VoIP", 5: "personnel", 6: "radiomessagerie", 7: "UAN",
    8: "inconnu", 9: "vocal gratuit", 10: "surtaxé", 27: "urgence",
}


class PhoneModule(OsintModule):
    name = "phone"
    description = (
        "Analyse un numéro de téléphone : validité, pays, opérateur probable, "
        "type de ligne (mobile/fixe/VoIP), fuseaux horaires. Gratuit, hors-ligne. "
        "Fournir de préférence au format international (ex: +33612345678)."
    )
    accepts = [InputType.PHONE]
    legal_notice = "Analyse locale de la structure du numéro (données publiques de numérotation)."

    def run(self, input_type: str, value: str, config: dict) -> ModuleResult:
        if input_type != InputType.PHONE.value:
            return ModuleResult(status="refused", detail="phone n'accepte qu'un numéro de téléphone.")

        try:
            import phonenumbers
            from phonenumbers import carrier, geocoder, number_type, timezone
        except ImportError:
            return ModuleResult(status="error", detail="Lib 'phonenumbers' non installée (voir install.sh).")

        raw = value.strip()
        parsed = None
        for region in (None, "FR"):  # tente le format international, puis FR en secours
            try:
                parsed = phonenumbers.parse(raw, region)
                break
            except phonenumbers.NumberParseException:
                continue
        if parsed is None:
            return ModuleResult(status="error", detail="Numéro illisible. Essaie le format international (+33…).")

        if not phonenumbers.is_valid_number(parsed):
            return ModuleResult(status="ok", entities=[], detail="Numéro invalide ou inexistant.")

        country = geocoder.description_for_number(parsed, "fr")
        op = carrier.name_for_number(parsed, "fr")
        tzs = list(timezone.time_zones_for_number(parsed))
        line = _TYPE_LABELS.get(int(number_type(parsed)), "inconnu")
        e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        intl = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)

        extra = {"operateur": op, "type_ligne": line, "fuseaux": tzs,
                 "format_e164": e164, "format_international": intl, "pays": country}
        entities = []
        if country:
            entities.append(ModuleResultEntity(type="location", value=country, extra={"source": "phone", **extra}))
        if op:
            entities.append(ModuleResultEntity(type="other", value=f"Opérateur: {op}", extra=extra))
        entities.append(ModuleResultEntity(type="other", value=f"Type: {line}", extra=extra))

        return ModuleResult(status="ok", entities=entities,
                            detail=f"{intl} — {country or 'pays inconnu'}, {line}"
                                   + (f", opérateur {op}" if op else "") + ".")
