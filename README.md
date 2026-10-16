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

## Matrice de mutations

`mutation_matrix.py` vérifie un cas nominal et quatre trajectoires fautives.
La matrice ne passe que si le nominal est accepté et si toutes les mutations
sont rejetées.

```bash
python3 scripts/mutation_matrix.py docs/hermes_trace_canonical.jsonl \
  docs/hermes_replay_fixtures.json \
  --allow-tool tau_real_portfolio_gate
```

## Comparaison d'agents

`compare_agents.py` applique le même replay et la même porte Tau à plusieurs
traces. Le manifest distingue les agents et leurs fixtures, afin de comparer
leurs trajectoires sans confondre une différence d'adaptateur avec une
différence de comportement.

```bash
python3 scripts/compare_agents.py docs/agent_comparison.json
```

## Porte de mission complète

La commande `scripts/mission_gate.py` enchaîne les trois niveaux : validation de
trace, replay déterministe, puis porte Tau. Elle ne lance Tau que si les deux
premières portes sont vertes.

```bash
python3 scripts/mission_gate.py docs/hermes_trace_canonical.jsonl \
  docs/hermes_replay_fixtures.json \
  --allow-tool tau_real_portfolio_gate
```

Le verdict est écrit dans `mission_verdict.json`. Un seul échec bloque la
mission et indique la couche fautive.

## Porte Tau émise depuis la trace

La mission ne rejoue pas un noyau figé. `scripts/emit_tau_trace.py` construit la
spec depuis la trace canonique : un fait ponctuel par pas, un lien indexé vers
l'appel du même `call_id`, et une mutation qui ajoute une négation au noyau
intact. Un appel sans décision antérieure vise l'indice 0, déjà épinglé à 0 :
le noyau est alors `UNSAT`.

```bash
python3 scripts/run_tau_gate.py --trace docs/hermes_trace_canonical.jsonl
```

`scripts/mission_gate.py` et `scripts/compare_agents.py` passent chacun par ce
chemin. Deux agents ne partagent plus le même verdict Tau.

## Lot de trajectoires

Sept chemins, sept formes. Le harness Python les accepte tous. Tau en accepte
4 et en refuse 3 : appel sans décision antérieure, décision placée après
l'appel, fin sans décision.

```bash
python3 scripts/trajectory_portfolio.py
```

Le rapport est `trajectory_portfolio.json`. Un lot sans forme distincte, ou
sans cas `UNSAT`, n'est pas une preuve.

## Porte Tau de transition, exemple manuel

Le noyau `tau/agent_transition.tau` reste l'exemple écrit à la main de la même
forme. `scripts/run_tau_gate.py` sans `--trace` l'exécute encore. Il ne juge
pas la trace passée à la mission.

```bash
python3 scripts/run_tau_gate.py
```

Le rapport est écrit dans `tau/verdict.json`. La CI exécute les tests Python ;
elle n'exécute pas Tau, le binaire n'y est pas installé.

## État du projet

- adaptateurs Hermes et Claude Code vers une trace canonique ;
- validation des outils, appels, résultats et terminaison ;
- replay déterministe par fixtures ;
- mutations : outil interdit, résultat orphelin, arrêt prématuré, résultat ignoré ;
- propriétés Tau émises depuis chaque trace, exécutées localement (`SAT` /
  `UNSAT` / contrôle libre) ;
- comparaison multi-agents sur la spec de chacun, pas sur un noyau partagé ;
- lot de 7 trajectoires distinctes : le harness les accepte toutes, Tau en
  refuse 3.

Le projet conserve volontairement une séparation stricte entre le runtime de
l'agent, l'adaptation de sa trace et la vérification indépendante.
