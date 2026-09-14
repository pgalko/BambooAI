#!/usr/bin/env python3
"""
One-time migration: OWL/TTL ontology -> memory pack YAML.

Standalone by design - the app-side ontology machinery is retired, so this
script carries its own minimal rdflib extraction (functions only). Run it on
a machine that has rdflib installed; the sandboxed app does not need it and
requirements.txt no longer lists it.

    pip install rdflib pyyaml
    python scripts/ttl_to_memory_pack.py web_app/ontologies/intervals_icu_ontology.ttl \
        --out my_memory_pack.yaml [--status established]

What converts: each ontology Function (the 17 intervals.icu methods) becomes
one method card - the nine annotation dimensions map onto hooks/body, the
typed relations onto relations, and the card enters as `taught: true` at the
status you choose (default: established, since a curated ontology is
user-authored knowledge). What deliberately does NOT convert: the ~144
measurement/data-dictionary entries. Per memory_pack_design.md, deployment
data semantics are probed by running code and taught at the moments they
matter, not carried as a bulk dictionary. Seeding is optional either way -
an empty pack is a valid, validated cold start.
"""

import argparse
import sys
from datetime import date

import yaml

try:
    from rdflib import Graph, RDF, Namespace, URIRef
except ImportError:
    sys.exit("rdflib is required: pip install rdflib")

ANNOT = {
    "answersQuestion": ("hooks", "answers_question"),
    "useWhen": ("hooks", "use_when"),
    "functionDefinition": ("body", "function_definition"),
    "assumes": ("body", "assumes"),
    "limitations": ("body", "limitations"),
    "physiologicalBasis": ("body", "rationale"),
    "interpretationGuide": ("body", "interpretation_guide"),
    "outputShape": ("body", "output_shape"),
    "errorBehavior": ("body", "error_behavior"),
    "defaultParameters": ("body", "default_parameters"),
}
RELATIONS = {
    "functionRequiresMeasurements": "requires",
    "functionRequiresDerivedMetrics": "requires",
    "dependsOnFunction": "depends_on",
    "producesOutputs": "produces",
    "alternativeTo": "alternative_to",
    "complementedBy": "complemented_by",
}


def local(uri):
    s = str(uri)
    return s.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ttl")
    ap.add_argument("--out", default="memory_pack.yaml")
    ap.add_argument("--status", default="established",
                    choices=["candidate", "established"])
    args = ap.parse_args()

    g = Graph()
    g.parse(args.ttl, format="turtle")
    ns = None
    for s, _, o in g.triples((None, RDF.type, None)):
        if local(o) == "Function":
            ns = Namespace(str(o).rsplit("#", 1)[0] + "#")
            break
    if ns is None:
        sys.exit("No :Function individuals found in the graph.")

    cards, skipped = [], []
    for fn in sorted(set(g.subjects(RDF.type, URIRef(ns + "Function")))):
        name = local(fn)
        card = {"name": name, "kind": "method", "status": args.status,
                "hooks": {}, "body": {}, "relations": {},
                "provenance": {"source": "converted",
                               "created": date.today().isoformat(),
                               "note": f"converted from {args.ttl}"},
                "taught": True, "use_count": 0, "last_used": None,
                "evidence": []}
        for pred, (sect, key) in ANNOT.items():
            vals = list(g.objects(fn, URIRef(ns + pred)))
            if vals:
                card[sect][key] = str(vals[0]).strip()
        for pred, key in RELATIONS.items():
            vals = sorted(local(o) for o in g.objects(fn, URIRef(ns + pred)))
            if vals:
                card["relations"].setdefault(key, [])
                card["relations"][key] += [v for v in vals
                                           if v not in card["relations"][key]]
        required = [card["hooks"].get("answers_question"),
                    card["hooks"].get("use_when"),
                    card["body"].get("function_definition"),
                    card["body"].get("assumes"),
                    card["body"].get("limitations")]
        if all(required):
            cards.append(card)
        else:
            skipped.append(name)

    names = {c["name"] for c in cards}
    for card in cards:
        for key in list(card["relations"]):
            kept = [r for r in card["relations"][key] if r in names]
            if kept:
                card["relations"][key] = kept
            else:
                del card["relations"][key]

    with open(args.out, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"version": 1, "cards": cards}, fh,
                       sort_keys=False, allow_unicode=True)
    print(f"{len(cards)} cards written to {args.out} "
          f"(status={args.status}, taught=true)")
    if skipped:
        print(f"skipped (missing required annotations): {', '.join(skipped)}")
    print("Relations pointing outside the converted set (measurements, "
          "derived metrics) were dropped: the pack only references cards "
          "it contains.")


if __name__ == "__main__":
    main()
