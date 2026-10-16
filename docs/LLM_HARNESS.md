# Harness LLM — première tranche

Le but est de vérifier un agent qui raisonne, appelle des outils et termine une
mission, qu'il s'agisse d'Hermès, de Claude Code ou d'un autre runtime.

## Tranche livrée

`scripts/llm_harness.py` rejoue une trace JSONL et contrôle :

- début par `session_start` ;
- types d'événements connus ;
- outils autorisés ;
- `call_id` unique ;
- correspondance `tool_call` / `tool_result` ;
- absence d'appel non résolu ;
- nombre maximal d'étapes ;
- présence d'un `session_end` terminal.

Exemple :

```bash
python3 scripts/llm_harness.py docs/llm_harness_example.jsonl \
  --allow-tool tau_real_portfolio_gate
```

## Pourquoi cette tranche sert l'objectif

Un harness LLM ne doit pas seulement comparer le texte final. Il doit contrôler
la trajectoire : quel outil a été appelé, avec quel identifiant, dans quel ordre,
et si l'agent a effectivement atteint un état terminal. La porte Tau fournit
ensuite la couche de propriétés temporelles et de mutations ; ce validateur
fournit le contrat d'adaptation entre un runtime d'agent et cette couche.

## Adaptateurs et replay

`scripts/llm_adapters.py` convertit les enregistrements Hermes et Claude Code
vers le format canonique. `scripts/llm_replay.py` compare ensuite les résultats
d'outils observés à un jeu de fixtures, sans rappeler les outils. Une différence
est classée comme non-déterminisme et fait échouer la porte.

```bash
python3 scripts/llm_adapters.py hermes input.jsonl normalized.jsonl
python3 scripts/llm_replay.py normalized.jsonl fixtures.json
```

## Suite livrée ensuite

1. propriétés Tau émises depuis la trace (`emit_tau_trace.py`), exécutées avec
   `tau -X -q -c false` : noyau `SAT`, négation `UNSAT`, sonde de lien `SAT`
   puis négation du conséquent `UNSAT`, contrôle libre `SAT` ;
2. mutations d'agent : outil interdit, appel orphelin, arrêt prématuré,
   résultat ignoré ;
3. comparaison des verdicts par agent, chacun sur sa propre spec ;
4. lot de trajectoires de formes différentes, dont des chemins que le harness
   accepte et que Tau refuse.

La CI ne lance pas Tau. Un test d'exécution est ignoré si le binaire est absent.

## Mutations négatives

`scripts/llm_mutations.py` fabrique des traces volontairement fautives : outil
interdit, résultat orphelin, arrêt prématuré et résultat ignoré. Chaque mutation
doit être refusée par le harness. C'est l'équivalent, pour la trajectoire d'un
agent, des mutations `UNSAT` utilisées par la porte Tau.

```bash
python3 scripts/llm_mutations.py trace.jsonl disallowed_tool mutated.jsonl
python3 scripts/llm_harness.py mutated.jsonl --allow-tool tau_real_portfolio_gate
```
