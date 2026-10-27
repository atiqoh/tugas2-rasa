"""
check_project.py - Pemeriksa konsistensi lintas komponen (pelengkap `rasa data validate`).

Memastikan nama intent/entity/slot/action/response konsisten antara:
  datasets/nlu_train.csv  <->  rasa-bot/domain.yml  <->  data/rules.yml & stories.yml
  <->  actions/actions.py  <->  NLU service (entity yang dihasilkan)
Jalankan dari root proyek:  python scripts/check_project.py
"""
import csv
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "rasa-bot"
DEFAULT_INTENTS = {"nlu_fallback", "session_start", "restart", "back", "out_of_scope"}
DEFAULT_ACTIONS = {"action_listen", "action_restart", "action_session_start",
                   "action_default_fallback", "action_deactivate_loop",
                   "action_revert_fallback_events", "action_default_ask_affirmation",
                   "action_default_ask_rephrase", "action_two_stage_fallback",
                   "action_unlikely_intent", "action_back", "action_extract_slots", "..."}
NLU_ENTITY_TYPES = {"product", "category", "order_id", "email"}

errors = []


def check(cond, msg):
    if not cond:
        errors.append(msg)


domain = yaml.safe_load((BOT / "domain.yml").read_text())
rules = yaml.safe_load((BOT / "data" / "rules.yml").read_text())["rules"]
stories = yaml.safe_load((BOT / "data" / "stories.yml").read_text())["stories"]
actions_src = (BOT / "actions" / "actions.py").read_text()

intents = set(domain["intents"])
entities = {list(e)[0] if isinstance(e, dict) else e for e in domain["entities"]}
slots = domain["slots"]
forms = domain["forms"]
responses = set(domain["responses"])
custom_actions = set(domain["actions"])
known_actions = responses | custom_actions | set(forms) | DEFAULT_ACTIONS
known_intents = intents | DEFAULT_INTENTS

# 1. label dataset NLU == intent domain
with open(ROOT / "datasets" / "nlu_train.csv", encoding="utf-8") as f:
    labels = {r["intent"] for r in csv.DictReader(f)}
check(labels == intents, f"Label NLU != intent domain: hanya-NLU={labels - intents}, "
                         f"hanya-domain={intents - labels}")
with open(ROOT / "datasets" / "nlu_test_heldout.csv", encoding="utf-8") as f:
    test_labels = {r["intent"] for r in csv.DictReader(f)}
check(test_labels <= labels, f"Label test tidak ada di train: {test_labels - labels}")

# 2. entity yang dihasilkan NLU service terdaftar di domain
check(NLU_ENTITY_TYPES <= entities, f"Entity NLU belum di domain: {NLU_ENTITY_TYPES - entities}")

# 3. rules & stories hanya memakai intent/action/slot/form yang dikenal
for kind, items in (("rule", rules), ("story", stories)):
    for it in items:
        name = it.get(kind)
        for st in it.get("condition", []) + it["steps"]:
            if "intent" in st:
                check(st["intent"] in known_intents, f"{kind} '{name}': intent {st['intent']}?")
                for ent in st.get("entities", []):
                    check(list(ent)[0] in entities, f"{kind} '{name}': entity {ent}?")
            if "action" in st:
                check(st["action"] in known_actions, f"{kind} '{name}': action {st['action']}?")
            if "active_loop" in st and st["active_loop"] is not None:
                check(st["active_loop"] in forms, f"{kind} '{name}': form {st['active_loop']}?")
            for sv in st.get("slot_was_set", []):
                key = list(sv)[0] if isinstance(sv, dict) else sv
                check(key in slots or key == "requested_slot", f"{kind} '{name}': slot {key}?")

# 4. slot mapping memakai entity/intent/form yang ada
for sname, sdef in slots.items():
    for m in sdef["mappings"]:
        if m["type"] == "from_entity":
            check(m["entity"] in entities, f"slot {sname}: entity {m['entity']}?")
        for key in ("intent", "not_intent"):
            vals = m.get(key)
            for v in ([vals] if isinstance(vals, str) else vals or []):
                check(v in known_intents, f"slot {sname}: {key} {v}?")
        for c in m.get("conditions", []):
            if c.get("active_loop"):
                check(c["active_loop"] in forms, f"slot {sname}: form {c['active_loop']}?")
                if c.get("requested_slot"):
                    check(c["requested_slot"] in forms[c["active_loop"]]["required_slots"],
                          f"slot {sname}: requested_slot {c['requested_slot']} bukan milik form")

# 5. form: slot ada, punya utter_ask_<slot>, dan ada validate_<form>
for fname, fdef in forms.items():
    for s in fdef["required_slots"]:
        check(s in slots, f"form {fname}: slot {s} tidak ada")
        check(f"utter_ask_{s}" in responses or f"utter_ask_{fname}_{s}" in responses,
              f"form {fname}: response utter_ask_{s} tidak ada")
    check(f"validate_{fname}" in custom_actions, f"validate_{fname} tidak terdaftar di domain")

# 6. actions.py <-> domain
names_py = set(re.findall(r'def name\(self\) -> Text:\s+return "([a-z_]+)"', actions_src))
check(names_py == custom_actions, f"actions.py vs domain: hanya-py={names_py - custom_actions},"
                                  f" hanya-domain={custom_actions - names_py}")
for r in set(re.findall(r'response="(utter_[a-z_]+)"', actions_src)):
    check(r in responses, f"actions.py memakai response {r} yang tidak ada di domain")
for s in set(re.findall(r'(?:SlotSet|get_slot)\("([a-z_]+)"', actions_src)):
    check(s in slots, f"actions.py memakai slot {s} yang tidak ada di domain")

# 7. payload tombol menunjuk intent yang ada
for rname, variants in domain["responses"].items():
    for v in variants:
        for b in v.get("buttons", []):
            m = re.match(r"^/([A-Za-z_]+)", b["payload"])
            check(m and m.group(1) in known_intents, f"{rname}: payload {b['payload']}?")
        for var in re.findall(r"\{([a-z_]+)\}", v.get("text", "")):
            check(var in slots, f"{rname}: variabel {{{var}}} bukan slot (pastikan diisi "
                                f"via kwargs dispatcher)")

# 8. config.yml & endpoints.yml
config = yaml.safe_load((BOT / "config.yml").read_text())
endpoints = yaml.safe_load((BOT / "endpoints.yml").read_text())
check(any(c["name"] == "NLUCommandAdapter" for c in config["pipeline"]),
      "NLUCommandAdapter tidak ada di pipeline")
check(endpoints.get("nlu", {}).get("url", "").startswith("http"), "endpoints.yml nlu.url kosong")
check(not (BOT / "data" / "nlu.yml").exists(),
      "data/nlu.yml ada -> Rasa akan mencoba melatih NLU internal")
check(not (BOT / "data" / "flows.yml").exists(), "hapus data/flows.yml (modul kuliah)")

used_intents = {st["intent"] for it in rules + stories for st in it["steps"] if "intent" in st}
unused = intents - used_intents
if unused:
    print(f"INFO: intent tanpa rule/story (diserahkan ke TEDPolicy/slot mapping): {sorted(unused)}")

if errors:
    print("GAGAL:")
    for e in errors:
        print("  -", e)
    sys.exit(1)
print(f"OK: {len(intents)} intent, {len(entities)} entity, {len(slots)} slot, {len(forms)} form, "
      f"{len(custom_actions)} custom action, {len(responses)} response, {len(rules)} rule, "
      f"{len(stories)} story - semua konsisten.")
