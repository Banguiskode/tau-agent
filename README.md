# Tau Agent

Harness indépendant pour agents LLM — Hermès, Claude Code et runtimes
compatibles — avec replay déterministe, mutations négatives et portes Tau.

## Objectif

Vérifier la trajectoire complète d'un agent, pas seulement son texte final :

```text
LLM → appel d'outil → résultat → décision → état terminal
```

## Démarrage rapide

```bash
python3 -m unittest discover -s scripts -p 'test_llm_*.py' -v
python3 scripts/llm_harness.py docs/llm_harness_example.jsonl \
  --allow-tool tau_real_portfolio_gate
```

## Adapter et rejouer une trace Hermès

```bash
python3 scripts/llm_adapters.py hermes \
  docs/hermes_trace_example.jsonl /tmp/hermes_normalized.jsonl
python3 scripts/llm_replay.py /tmp/hermes_normalized.jsonl \
  docs/hermes_replay_fixtures.json
```

## Tester les comportements interdits

```bash
python3 scripts/llm_mutations.py /tmp/hermes_normalized.jsonl \
  disallowed_tool /tmp/mutated.jsonl
python3 scripts/llm_harness.py /tmp/mutated.jsonl \
  --allow-tool tau_real_portfolio_gate
```

Le dernier contrôle doit échouer : un échec sur une trace mutée est une preuve
que la porte rejette le comportement interdit.

## État du projet

- adaptateurs Hermes et Claude Code vers une trace canonique ;
- validation des outils, appels, résultats et terminaison ;
- replay déterministe par fixtures ;
- mutations : outil interdit, résultat orphelin, arrêt prématuré, résultat ignoré ;
- propriétés Tau et comparaison multi-modèles : prochaines tranches.

Le projet conserve volontairement une séparation stricte entre le runtime de
l'agent, l'adaptation de sa trace et la vérification indépendante.
