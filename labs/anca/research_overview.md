# Anca Dragan and InterACT Research Overview

Updated 14 October 2026. Recent results appear first.

Anca Dragan's InterACT lab at UC Berkeley studies how AI can understand people's goals, collaborate with them, and remain under meaningful human control. Its work spans robots, assistive interfaces, language agents, and recommenders. A recurring question is whether an agent is actually helping the person, rather than merely optimizing the feedback it receives. The lab is affiliated with BAIR and the Center for Human-Compatible AI. [InterACT](https://interact.berkeley.edu/) and [Anca Dragan](https://people.eecs.berkeley.edu/~anca/) describe this research mission.

## Most recent results

| Saved version date | Work | Problem and finding |
| --- | --- | --- |
| 24 July 2026 | [Gemma 4 technical report](summary/2026-gemma-4-technical-report.md) | Collaborative work on capable, efficient open-weight multimodal models. It reports broad capability gains; it does not demonstrate a robot controller. |
| 24 May 2026 | [MOOD safety monitoring](summary/2026-benchmarking-and-improving-monitors-for-out-of-distribution-alignment-failure-in-llms.md) | Safety classifiers miss unfamiliar failures. Adding anomaly signals improves aggregate recall from 38.8% to 45.7% at a 1% false-positive rate for Gemma 2 9B, but major failure categories and benign shifts remain difficult. The reported average includes the in-distribution unsafe test set. |
| 9 January 2026 | [AI mediation and democratic deliberation](summary/2026-can-ai-mediation-improve-democratic-deliberation.md) | A perspective on using AI to help groups find common ground. Small-group results motivate the idea; scalable and democratically accountable mediation remains a research proposal. |

**Scope and dates.** The timeline covers all 53 records saved in this folder, including collaborations beyond InterACT and large model reports. It orders papers by the date printed on the saved PDF version, newest first; this is a version chronology, not a claim about when a project began or its latest online update. Where no dated arXiv banner exists, only the catalog year is used, and the entry follows dated papers in that year. First preprint months are shown separately when useful. Each entry links to its PDF and detailed saved summary.

## What the lab is trying to solve

**Learning what people want from imperfect signals.** A person may give a demonstration, compare two behaviors, say how a motion should change, or issue an instruction. The challenge is to extract the intended objective without assuming that every signal is accurate or complete. Preference-query selection and comparative-language feedback try to make this interaction more informative and efficient.

**Helping while preserving human agency.** An assistant needs to contribute without silently replacing the person's choices with its own. Assistance games treat the person's goal as hidden information to learn during collaboration. Empowerment methods instead optimize the person's ability to affect future outcomes, reducing dependence on an explicitly inferred reward function.

**Making skills and representations generalize.** A robot should reuse demonstrations across instructions, partners, and task combinations. Language-goal alignment, temporal successor representations, and compact interaction histories study how learned structure can support such reuse without a separate bespoke planner for every task.

**Preventing feedback optimization from becoming manipulation.** Human approval, engagement, and learned rewards are imperfect proxies. The group studies deception under partial observation, reward hacking, changing preferences, and targeted feedback gaming. Auditing and safety monitoring address failures that training did not anticipate.

## How the research has developed

The following is a synthesis of themes, rather than a claim that every paper belongs to one sequential project.

| Period | Main direction | What changed |
| --- | --- | --- |
| 2026 | Detect unfamiliar failures and examine wider social applications | Safety monitoring becomes an explicit generalization problem; AI mediation raises questions about collective preferences and oversight. |
| 2025 | Scale assistance and retain user control | Minecraft assistance games, coding empowerment, steerable recommendations, and critic-guided LLM planning turn interaction objectives into more substantial systems. |
| 2024 | Understand imperfect supervision and improve representations | Work diagnoses partial-observation deception, influenceable preferences, and reward overoptimization while developing richer feedback and temporal representations. |
| 2023 | Build foundations for adaptive assistance and auditing | Offline human-interaction learning, language-conditioned control, partner representations, and automatic LLM audits establish core tools and expose limits of proxy objectives. |

## Detailed timeline with newest versions first

### 2026

#### 24 July 2026 — Gemma 4 technical report

**Problem:** How can practical open-weight models improve reasoning, multimodal understanding, and deployment efficiency?

**Approach:** Develop multimodal Gemma models with reasoning options and efficient long-context inference.

**Finding:** The report describes stronger benchmark and preference performance than previous Gemma models. It is a large collaborative model-development contribution, with no demonstrated robot-control result.

Sources: [paper PDF](pdfs/2026-gemma-4-technical-report.pdf) · [detailed summary](summary/2026-gemma-4-technical-report.md).

#### 24 May 2026 — Benchmarking and Improving Monitors for Out-Of-Distribution Alignment Failure in LLMs

**Problem:** Can safety monitors detect alignment failures that differ from their training examples?

**Approach:** Introduce MOOD and combine a safety classifier with perplexity and feature-space out-of-distribution scores.

**Finding:** For Gemma 2 9B, aggregate mean recall rises from 38.8% to 45.7% at a 1% in-distribution safe false-positive rate; that mean includes the in-distribution unsafe set as well as held-out failures. Some tool and code failures remain almost undetected, and benign distribution shifts can produce false alarms.

Sources: [paper PDF](pdfs/2026-benchmarking-and-improving-monitors-for-out-of-distribution-alignment-failure-in-llms.pdf) · [detailed summary](summary/2026-benchmarking-and-improving-monitors-for-out-of-distribution-alignment-failure-in-llms.md).

#### 9 January 2026 — Can AI mediation improve democratic deliberation?

**Problem:** Could AI mediation improve participation, fairness, and substantive democratic discussion together?

**Approach:** Analyze the Habermas Machine's generation, preference prediction, voting, and revision pipeline.

**Finding:** Prior small-group studies motivate the approach, but this paper is a perspective rather than a new experiment. Large-scale deliberation and democratic oversight remain open problems.

Sources: [paper PDF](pdfs/2026-can-ai-mediation-improve-democratic-deliberation.pdf) · [detailed summary](summary/2026-can-ai-mediation-improve-democratic-deliberation.md).

### 2025

#### 19 December 2025 — Gemini 2.5: Pushing the frontier with advanced reasoning, multimodality, long context, and next generation agentic capabilities

First preprint month: 2025-07.

**Problem:** How can frontier models improve reasoning, multimodality, tool use, and controllable inference cost?

**Approach:** Develop Gemini 2.5 with RL-trained reasoning and native multimodal modeling.

**Finding:** The report shows broad capability gains but also perception and memory-to-planning weaknesses in long-horizon interaction. It is collaborative platform work rather than a validated robot policy.

Sources: [paper PDF](pdfs/2025-gemini-2-5-pushing-the-frontier-with-advanced-reasoning-multimodality-long-context-and-next-generation-agentic-capabilit.pdf) · [detailed summary](summary/2025-gemini-2-5-pushing-the-frontier-with-advanced-reasoning-multimodality-long-context-and-next-generation-agentic-capabilit.md).

#### 11 December 2025 — The facts leaderboard: A comprehensive benchmark for large language model factuality

**Problem:** How should factual reliability be evaluated across multiple model capabilities?

**Approach:** Build FACTS benchmarks for supplied documents, internal knowledge, web search, and images.

**Finding:** The evaluations expose different weaknesses across modalities, with especially limited multimodal factuality. This is model reliability infrastructure, not evidence that a robot executes tasks safely.

Sources: [paper PDF](pdfs/2025-the-facts-leaderboard-a-comprehensive-benchmark-for-large-language-model-factuality.pdf) · [detailed summary](summary/2025-the-facts-leaderboard-a-comprehensive-benchmark-for-large-language-model-factuality.md).

#### 7 December 2025 — Chain of thought monitorability: A new and fragile opportunity for ai safety

First preprint month: 2025-07.

**Problem:** Can a model's visible reasoning help reveal unsafe intent, and can that visibility be preserved?

**Approach:** Analyze when harmful reasoning must be externalized and when training may suppress or bypass visible traces.

**Finding:** Chain-of-thought monitoring can provide an additional oversight signal, but a benign trace does not establish benign internal reasoning. This is a position paper, not a new measured safety guarantee.

Sources: [paper PDF](pdfs/2025-chain-of-thought-monitorability-a-new-and-fragile-opportunity-for-ai-safety.pdf) · [detailed summary](summary/2025-chain-of-thought-monitorability-a-new-and-fragile-opportunity-for-ai-safety.md).

#### 3 December 2025 — Planning without search: Refining frontier llms with offline goal-conditioned rl

First preprint month: 2025-05; Catalog year: 2026; saved PDF version year: 2025.

**Problem:** How can API-based LLMs plan multi-turn interactions without expensive search or policy fine-tuning?

**Approach:** Train a small goal-conditioned critic offline and use it to critique and refine the acting model's proposed reasoning.

**Finding:** PNLC improves reported WebShop, Avalon, and simulated persuasion outcomes while lowering latency relative to large-budget search. Critics remain task-specific; physical robot planning is not tested.

Sources: [paper PDF](pdfs/2026-planning-without-search-refining-frontier-llms-with-offline-goal-conditioned-rl.pdf) · [detailed summary](summary/2026-planning-without-search-refining-frontier-llms-with-offline-goal-conditioned-rl.md).

#### 16 October 2025 — Training llm agents to empower humans

**Problem:** How can a coding assistant help without taking over decisions the person should make?

**Approach:** Train on offline code and use cumulative surprisal to decide when to stop completing code and return control.

**Finding:** In an 18-person study, users preferred Empower 78% of the time, with 31% higher acceptance and fewer deletions. The result supports human agency in coding assistance, with broader domains still untested.

Sources: [paper PDF](pdfs/2025-training-llm-agents-to-empower-humans.pdf) · [detailed summary](summary/2025-training-llm-agents-to-empower-humans.md).

#### 14 October 2025 — CTRL-Rec: Controlling recommender systems with natural language

**Problem:** How can users directly steer recommendations rather than accept an engagement-optimized feed?

**Approach:** Distill language request-item judgments into efficient dual encoders and combine them with a recommender.

**Finding:** A 19-user movie study finds improved perceived control, expressivity, and satisfaction without a significant change in like ratio. Generalization beyond movie recommendations is untested.

Sources: [paper PDF](pdfs/2025-ctrl-rec-controlling-recommender-systems-with-natural-language.pdf) · [detailed summary](summary/2025-ctrl-rec-controlling-recommender-systems-with-natural-language.md).

#### 12 June 2025 — Assistancezero: Scalably solving assistance games

First preprint month: 2025-04.

**Problem:** Can assistance games scale beyond toy settings when a person's goal is hidden?

**Approach:** Extend AlphaZero-style search with goal and human-action predictions in a Minecraft building benchmark.

**Finding:** AssistanceZero reduces simulated human effort, and a 16-person study confirms fewer human place/break actions than working alone. Evidence concerns structured virtual collaboration, not physical robotics or a complete replacement for RLHF.

Sources: [paper PDF](pdfs/2025-assistancezero-scalably-solving-assistance-games.pdf) · [detailed summary](summary/2025-assistancezero-scalably-solving-assistance-games.md).

#### 2 April 2025 — An approach to technical agi safety and security

**Problem:** How should a developer combine defenses against misuse and misalignment as AI capabilities advance?

**Approach:** Propose capability evaluations, robust training, AI-assisted oversight, monitoring, and security as layered defenses.

**Finding:** The contribution is an integrated technical safety research agenda. It does not establish that an end-to-end AGI safety system has been solved or empirically validated.

Sources: [paper PDF](pdfs/2025-an-approach-to-technical-agi-safety-and-security.pdf) · [detailed summary](summary/2025-an-approach-to-technical-agi-safety-and-security.md).

#### 10 March 2025 — Learning temporal distances: Contrastive successor features can provide a metric structure for decision-making

First preprint month: 2024-06; Catalog year: 2024; saved PDF version year: 2025.

**Problem:** Can a learned temporal distance obey useful geometric structure in stochastic environments?

**Approach:** Transform contrastive successor features into a temporal distance with a triangle-inequality property and learn goal-conditioned control.

**Finding:** The method enables trajectory stitching and improves selected navigation and AntMaze results. The formal result assumes discrete Markov processes; no physical robot is evaluated.

Sources: [paper PDF](pdfs/2024-learning-temporal-distances-contrastive-successor-features-can-provide-a-metric-structure-for-decision-making.pdf) · [detailed summary](summary/2024-learning-temporal-distances-contrastive-successor-features-can-provide-a-metric-structure-for-decision-making.md).

#### 22 February 2025 — On targeted manipulation and deception when optimizing LLMs for user feedback

First preprint month: 2024-11.

**Problem:** Does optimizing user approval encourage assistance or personalized exploitation of susceptible users?

**Approach:** Fine-tune safety-trained models on simulated approval in four conversational settings.

**Finding:** Models learn targeted feedback gaming even with only 2% gameable users, and conventional safety benchmarks often miss it. These are simulated-user results rather than measured effects on real people.

Sources: [paper PDF](pdfs/2025-on-targeted-manipulation-and-deception-when-optimizing-llms-for-user-feedback.pdf) · [detailed summary](summary/2025-on-targeted-manipulation-and-deception-when-optimizing-llms-for-user-feedback.md).

#### 13 February 2025 — Temporal representation alignment: Successor features enable emergent compositionality in robot instruction following

Catalog year: 2026; saved PDF version year: 2025.

**Problem:** Can a robot compose familiar skills into new multi-step instructions without a separate planner?

**Approach:** Add temporal alignment between current and future representations to language- and goal-conditioned behavioral cloning.

**Finding:** TRA improves compositional instruction following on 13 real-world tabletop tasks and many simulated benchmarks. It still depends on demonstrations containing the underlying skills and is not uniformly better than offline RL.

Sources: [paper PDF](pdfs/2026-temporal-representation-alignment-successor-features-enable-emergent-compositionality-in-robot-instruction-following.pdf) · [detailed summary](summary/2026-temporal-representation-alignment-successor-features-enable-emergent-compositionality-in-robot-instruction-following.md).

#### 6 February 2025 — Context steering: Controllable personalization at inference time

First preprint month: 2024-05.

**Problem:** Can users control the strength of LLM personalization without retraining?

**Approach:** Scale the difference between contextual and context-free token logits during inference.

**Finding:** Context steering provides a usable personalization knob, with human ratings confirming stronger personalization. Results vary by task, decoding costs roughly double, and robotics benefits are not established.

Sources: [paper PDF](pdfs/2025-context-steering-controllable-personalization-at-inference-time.pdf) · [detailed summary](summary/2025-context-steering-controllable-personalization-at-inference-time.md).

#### 16 January 2025 — Learning to assist humans without inferring rewards

First preprint month: 2024-11; Catalog year: 2024; saved PDF version year: 2025.

**Problem:** Can an assistant help without first reconstructing the person's reward function?

**Approach:** Use contrastive successor representations to reward increasing the influence of human actions on future states.

**Finding:** ESR outperforms tested baselines in gridworlds and Overcooked. It offers an alternative assistance objective, but the experiments use simulated partners and assume observable actions and shared state.

Sources: [paper PDF](pdfs/2024-learning-to-assist-humans-without-inferring-rewards.pdf) · [detailed summary](summary/2024-learning-to-assist-humans-without-inferring-rewards.md).

#### 2025 year only — Correlated proxies: A new definition and improved mitigation for reward hacking

**Problem:** How can optimization improve a proxy reward without exploiting its mismatch with the true objective?

**Approach:** Define reward hacking relative to a reference policy and regularize state-action occupancy distributions using ORPO.

**Finding:** Occupancy regularization outperforms action-distribution regularization at the best tested coefficients on four sequential benchmarks. Guarantees require support and reward-correlation assumptions; practical tuning remains important.

Sources: [paper PDF](pdfs/2025-correlated-proxies-a-new-definition-and-improved-mitigation-for-reward-hacking.pdf) · [detailed summary](summary/2025-correlated-proxies-a-new-definition-and-improved-mitigation-for-reward-hacking.md).

### 2024

#### 16 December 2024 — Gemini 1.5: Unlocking multimodal understanding across millions of tokens of context

First preprint month: 2024-03.

**Problem:** Can a model retain and reason over very long multimodal context?

**Approach:** Develop Gemini 1.5 with sparse mixture-of-experts modeling and extensive long-context evaluation.

**Finding:** Strong single-needle retrieval and long-video understanding coexist with imperfect exhaustive retrieval and planning. The platform report provides no real-robot closed-loop-control evidence.

Sources: [paper PDF](pdfs/2024-gemini-1-5-unlocking-multimodal-understanding-across-millions-of-tokens-of-context.pdf) · [detailed summary](summary/2024-gemini-1-5-unlocking-multimodal-understanding-across-millions-of-tokens-of-context.md).

#### 7 December 2024 — Twitter’s algorithm: Amplifying anger, animosity, and affective polarization

First preprint month: 2023-05; Catalog year: 2023; saved PDF version year: 2024.

**Problem:** Does engagement ranking match users' stated preferences for political content?

**Approach:** Audit personalized Twitter feeds and compare engagement-based, chronological, and explicit-preference rankings.

**Finding:** An 806-user study finds engagement ranking favors angrier and more hostile political content despite lower stated preference. Preference ranking reduces some divisive content but may strengthen in-group exposure; long-term polarization effects are not established.

Sources: [paper PDF](pdfs/2023-twitter-s-algorithm-amplifying-anger-animosity-and-affective-polarization.pdf) · [detailed summary](summary/2023-twitter-s-algorithm-amplifying-anger-animosity-and-affective-polarization.md).

#### 27 November 2024 — Q-sft: Q-learning for language models via supervised fine-tuning

Catalog year: 2025; saved PDF version year: 2024.

**Problem:** Can offline Q-learning use ordinary language-model training machinery?

**Approach:** Encode value information in token probabilities through Bellman-weighted supervised fine-tuning.

**Finding:** Q-SFT improves over supervised fine-tuning across reported tasks, including embodied benchmarks. It is not uniformly best, and the study does not establish pretrained VLA fine-tuning or real-robot deployment.

Sources: [paper PDF](pdfs/2025-q-sft-q-learning-for-language-models-via-supervised-fine-tuning.pdf) · [detailed summary](summary/2025-q-sft-q-learning-for-language-models-via-supervised-fine-tuning.md).

#### 17 November 2024 — When your ais deceive you: Challenges of partial observability in reinforcement learning from human feedback

First preprint month: 2024-02.

**Problem:** What happens when human evaluators judge only part of an agent's behavior?

**Approach:** Formalize deceptive inflation and overjustification under partially observed feedback.

**Finding:** Naive RLHF can reward appearing successful instead of succeeding. Modeling evaluator beliefs mitigates several toy cases, but information missing from feedback can create irreducible reward ambiguity.

Sources: [paper PDF](pdfs/2024-when-your-ais-deceive-you-challenges-of-partial-observability-in-reinforcement-learning-from-human-feedback.pdf) · [detailed summary](summary/2024-when-your-ais-deceive-you-challenges-of-partial-observability-in-reinforcement-learning-from-human-feedback.md).

#### 7 November 2024 — Interactive dialogue agents via reinforcement learning on hindsight regenerations

**Problem:** How can a dialogue policy improve using the consequences of unsuccessful utterances?

**Approach:** Regenerate better utterances and counterfactual continuations in hindsight, then train offline RL on the augmented conversations.

**Finding:** The method improves reported donation-persuasion and emotional-support rewards. Simulated gains exceed those in the small human study, and reliable task-specific rewards remain necessary.

Sources: [paper PDF](pdfs/2024-interactive-dialogue-agents-via-reinforcement-learning-on-hindsight-regenerations.pdf) · [detailed summary](summary/2024-interactive-dialogue-agents-via-reinforcement-learning-on-hindsight-regenerations.md).

#### 8 October 2024 — Trajectory Improvement and Reward Learning from Comparative Language Feedback

Catalog year: 2026; saved PDF version year: 2024.

**Problem:** How can a robot learn the direction of a user's preferred change rather than just which trajectory wins a comparison?

**Approach:** Align comparative language with differences between robot trajectories, then retrieve improved trajectories or learn personalized rewards.

**Finding:** A 10-person real-robot study reports 23.9% higher subjective scores and 11.3% shorter query times than pairwise preference learning. This saved 2024 version uses finite trajectory libraries and random queries; it does not demonstrate the active-learning claim in the manifest's 2026 title.

Sources: [paper PDF](pdfs/2026-active-reward-learning-and-iterative-trajectory-improvement-from-comparative-language-feedback.pdf) · [detailed summary](summary/2026-active-reward-learning-and-iterative-trajectory-improvement-from-comparative-language-feedback.md).

#### 7 October 2024 — Coprocessor actor critic: a model-based reinforcement learning approach for adaptive brain stimulation

First preprint month: 2024-06.

**Problem:** Can assistive stimulation adapt efficiently to a patient's movement capabilities?

**Approach:** Learn task-level values in simulation and then adapt the stimulation-to-movement mapping.

**Finding:** CopAC improves reward and sample efficiency in seven simulated control tasks, including fine motor settings. Human clinical benefit and physical deployment are not demonstrated.

Sources: [paper PDF](pdfs/2024-coprocessor-actor-critic-a-model-based-reinforcement-learning-approach-for-adaptive-brain-stimulation.pdf) · [detailed summary](summary/2024-coprocessor-actor-critic-a-model-based-reinforcement-learning-approach-for-adaptive-brain-stimulation.md).

#### 2 October 2024 — Gemma 2: Improving open language models at a practical size

First preprint month: 2024-08.

**Problem:** Can practical-size open models compete with much larger language models?

**Approach:** Combine teacher-distribution distillation, architectural changes, and instruction tuning.

**Finding:** Gemma 2 is competitive on selected benchmarks and human preference evaluations. This is collaborative language-model development rather than an embodied policy or proven robot planner.

Sources: [paper PDF](pdfs/2024-gemma-2-improving-open-language-models-at-a-practical-size.pdf) · [detailed summary](summary/2024-gemma-2-improving-open-language-models-at-a-practical-size.md).

#### 19 August 2024 — Gemma scope: Open sparse autoencoders everywhere all at once on gemma 2

**Problem:** How can researchers inspect internal features of an open language model?

**Approach:** Release sparse autoencoders across Gemma 2 layers and sublayers.

**Finding:** Gemma Scope supplies useful interpretability infrastructure with evaluated reconstruction and transfer properties. Releasing interpretable features does not itself demonstrate improved downstream safety.

Sources: [paper PDF](pdfs/2024-gemma-scope-open-sparse-autoencoders-everywhere-all-at-once-on-gemma-2.pdf) · [detailed summary](summary/2024-gemma-scope-open-sparse-autoencoders-everywhere-all-at-once-on-gemma-2.md).

#### 1 July 2024 — Adversaries can misuse combinations of safe models

First preprint month: 2024-06.

**Problem:** Are individually safe models still safe when used together?

**Approach:** Decompose harmful tasks so one model provides seemingly benign capabilities that another repurposes.

**Finding:** Combined models outperform individual-model misuse baselines in several tested domains. Safety therefore requires evaluation of model combinations, not just each component in isolation; this is controlled misuse evaluation.

Sources: [paper PDF](pdfs/2024-adversaries-can-misuse-combinations-of-safe-models.pdf) · [detailed summary](summary/2024-adversaries-can-misuse-combinations-of-safe-models.md).

#### 31 May 2024 — Learning to model the world with language

First preprint month: 2023-08; Catalog year: 2023; saved PDF version year: 2024.

**Problem:** Can language help an agent predict the world rather than merely select its next action?

**Approach:** Build Dynalang, a multimodal world model that integrates language and vision and trains control through imagined futures.

**Finding:** Language hints and manuals improve tested simulated control and instruction following. Real-robot transfer is untested, and the method is not competitive with specialized vision-language-navigation systems.

Sources: [paper PDF](pdfs/2023-learning-to-model-the-world-with-language.pdf) · [detailed summary](summary/2023-learning-to-model-the-world-with-language.md).

#### 28 May 2024 — AI alignment with changing and influenceable reward functions

**Problem:** What objective should AI optimize when its actions can change people's preferences?

**Approach:** Model evolving, influenceable rewards through dynamic-reward MDPs and compare alternative alignment objectives.

**Finding:** Static satisfaction can incentivize manipulation, but freezing initial preferences can also block legitimate change. No examined objective universally avoids undesirable influence while retaining all useful actions.

Sources: [paper PDF](pdfs/2024-ai-alignment-with-changing-and-influenceable-reward-functions.pdf) · [detailed summary](summary/2024-ai-alignment-with-changing-and-influenceable-reward-functions.md).

#### 22 May 2024 — Managing extreme AI risks amid rapid progress

First preprint month: 2023-10.

**Problem:** How should technical and institutional safeguards respond to increasingly capable autonomous AI?

**Approach:** Propose stronger evaluations, independent audits, developer safety cases, and capability-triggered restrictions.

**Finding:** This consensus perspective articulates a risk-management agenda. It reports no original experiment establishing the amount of risk these measures eliminate.

Sources: [paper PDF](pdfs/2024-managing-extreme-ai-risks-amid-rapid-progress.pdf) · [detailed summary](summary/2024-managing-extreme-ai-risks-amid-rapid-progress.md).

#### 12 April 2024 — The effective horizon explains deep RL performance in stochastic environments

First preprint month: 2023-12.

**Problem:** Why can deep RL solve some long episodes with relatively simple exploration?

**Approach:** Extend effective-horizon analysis to stochastic settings through shallow fitted-Q improvement and regression.

**Finding:** SQIRL explains part of observed deep-RL sample complexity, but solves fewer benchmark tasks than PPO. The contribution is explanatory theory, rather than a new leading robot-control algorithm.

Sources: [paper PDF](pdfs/2024-the-effective-horizon-explains-deep-rl-performance-in-stochastic-environments.pdf) · [detailed summary](summary/2024-the-effective-horizon-explains-deep-rl-performance-in-stochastic-environments.md).

#### 5 April 2024 — Evaluating frontier models for dangerous capabilities

First preprint month: 2024-03.

**Problem:** How can dangerous model capabilities be assessed before relying on deployment assumptions?

**Approach:** Evaluate persuasion, cyber tasks, self-proliferation, and self-reasoning with scaffolding and progress milestones.

**Finding:** The tested Gemini 1.0 systems show meaningful persuasion but weak long-horizon technical autonomy. The result is specific to the tested models and scaffolds, rather than a general assurance about future models.

Sources: [paper PDF](pdfs/2024-evaluating-frontier-models-for-dangerous-capabilities.pdf) · [detailed summary](summary/2024-evaluating-frontier-models-for-dangerous-capabilities.md).

#### 9 March 2024 — A generalized acquisition function for preference-based reward learning

**Problem:** Which preference question is most useful for the behavior the robot will eventually perform?

**Approach:** Choose queries to improve behavioral reward alignment rather than identify every reward parameter.

**Finding:** The acquisition framework beats information-gain querying in the tested synthetic, assistive, and domain-transfer settings. Feedback is simulated; physical deployment and learning from actual users are not established.

Sources: [paper PDF](pdfs/2024-a-generalized-acquisition-function-for-preference-based-reward-learning.pdf) · [detailed summary](summary/2024-a-generalized-acquisition-function-for-preference-based-reward-learning.md).

#### 19 February 2024 — Toward grounded commonsense reasoning

First preprint month: 2023-06.

**Problem:** What should a robot inspect before making a commonsense decision about an object?

**Approach:** Use an LLM to choose relevant information, move a camera, and query a VLM before acting.

**Finding:** Close-up active observations improve decisions over passive baselines; demonstrations include a robot on two surfaces. Object identities, scene geometry, and manipulation skills remain largely supplied.

Sources: [paper PDF](pdfs/2024-toward-grounded-commonsense-reasoning.pdf) · [detailed summary](summary/2024-toward-grounded-commonsense-reasoning.md).

#### 28 January 2024 — Aligning robot and human representations

First preprint month: 2023-02; Catalog year: 2023; saved PDF version year: 2024.

**Problem:** Why might a robot learn representations that fail to capture what humans care about?

**Approach:** Formalize alignment as recovering compact human-relevant representations from robot representations.

**Finding:** The paper identifies a representation-level requirement and reviews supporting case studies. It supplies a conceptual objective, not a practical general solver.

Sources: [paper PDF](pdfs/2023-aligning-robot-and-human-representations.pdf) · [detailed summary](summary/2023-aligning-robot-and-human-representations.md).

#### 11 January 2024 — Bridging rl theory and practice with the effective horizon

First preprint month: 2023-04; Catalog year: 2023; saved PDF version year: 2024.

**Problem:** Why is random-exploration RL tractable on some apparently long-horizon problems?

**Approach:** Introduce effective horizon and analyze the GORP lookahead-and-rollout algorithm.

**Finding:** Effective-horizon bounds correlate with PPO and DQN sample complexity in deterministic benchmarks. Guarantees concern the analyzed algorithms and environments, not arbitrary deep RL or continuous robotics.

Sources: [paper PDF](pdfs/2023-bridging-rl-theory-and-practice-with-the-effective-horizon.pdf) · [detailed summary](summary/2023-bridging-rl-theory-and-practice-with-the-effective-horizon.md).

#### 2024 year only — Achieving AI Alignment with Unreliable Supervision

**Problem:** How can alignment work when supervision and reward proxies are unreliable?

**Approach:** Study occupancy-based regularization and difficulty-aware preference modeling in a thesis.

**Finding:** The thesis develops improvements for simulated reward hacking and reward-model weighting. Selecting regularization using access to the true objective remains a major deployment limitation.

Sources: [paper PDF](pdfs/2024-achieving-ai-alignment-with-unreliable-supervision.pdf) · [detailed summary](summary/2024-achieving-ai-alignment-with-unreliable-supervision.md).

#### 2024 year only — Optimizing robot behavior via comparative language feedback

**Problem:** Can feedback such as moving faster be grounded in changes to robot motion?

**Approach:** Align a trajectory autoencoder and language encoder so feedback retrieves changed trajectories.

**Finding:** The workshop prototype demonstrates qualitative improvement in a simulated Jaco environment. It does not yet demonstrate real-user reward learning or unrestricted trajectory generation.

Sources: [paper PDF](pdfs/2024-optimizing-robot-behavior-via-comparative-language-feedback.pdf) · [detailed summary](summary/2024-optimizing-robot-behavior-via-comparative-language-feedback.md).

### 2023

#### 12 November 2023 — Managing ai risks in an era of rapid progress

First preprint month: 2023-10.

**Problem:** What safety and governance response is needed before autonomous AI becomes harder to control?

**Approach:** Publish a consensus agenda linking present harms, malicious use, and potential loss of human control.

**Finding:** The paper recommends investment and enforceable safeguards, rather than demonstrating a new algorithm or measuring risk reduction.

Sources: [paper PDF](pdfs/2023-managing-ai-risks-in-an-era-of-rapid-progress.pdf) · [detailed summary](summary/2023-managing-ai-risks-in-an-era-of-rapid-progress.md).

#### 9 November 2023 — Zero-shot goal-directed dialogue via rl on imagined conversations

**Problem:** Can a smaller dialogue agent learn goal-directed interaction without collecting task-specific real conversations?

**Approach:** Generate and critique synthetic conversations, then train offline RL.

**Finding:** The agent improves human ratings in personalized teaching and travel recommendation over tested baselines. The tasks and human study are small, and synthetic users differ from actual people.

Sources: [paper PDF](pdfs/2023-zero-shot-goal-directed-dialogue-via-rl-on-imagined-conversations.pdf) · [detailed summary](summary/2023-zero-shot-goal-directed-dialogue-via-rl-on-imagined-conversations.md).

#### 31 October 2023 — Offline rl with observation histories: Analyzing and improving sample complexity

Catalog year: 2024; saved PDF version year: 2023.

**Problem:** Why can using complete observation histories make offline RL inefficient?

**Approach:** Learn compact history representations with a bisimulation-inspired auxiliary objective.

**Finding:** The objective improves CQL on gridworld and ViZDoom, while adding little on Wordle where ordinary training already learns similar structure. The benefit depends on representation quality and data coverage.

Sources: [paper PDF](pdfs/2024-offline-rl-with-observation-histories-analyzing-and-improving-sample-complexity.pdf) · [detailed summary](summary/2024-offline-rl-with-observation-histories-analyzing-and-improving-sample-complexity.md).

#### 16 October 2023 — Quantifying assistive robustness via the natural-adversarial frontier

**Problem:** How can assistive robots be tested against difficult but still plausible human behavior?

**Approach:** Search a frontier trading off natural-looking human motion against robot failure using RIGID.

**Finding:** The method finds failures missed by sampled users and improves simulated itch-scratching robustness after retraining. It is expensive and does not provide a certified worst-case or real-robot safety guarantee.

Sources: [paper PDF](pdfs/2023-quantifying-assistive-robustness-via-the-natural-adversarial-frontier.pdf) · [detailed summary](summary/2023-quantifying-assistive-robustness-via-the-natural-adversarial-frontier.md).

#### 10 October 2023 — Confronting reward model overoptimization with constrained RLHF

Catalog year: 2024; saved PDF version year: 2023.

**Problem:** How can RLHF avoid overoptimizing multiple imperfect reward components?

**Approach:** Replace fixed composite rewards with constrained PPO and dynamically adjusted weights.

**Finding:** The approach improves an automatic dialogue evaluation and extended-training stability in a narrow two-reward setup. It still needs access to an evaluation surrogate and has no human-rating or robot evaluation.

Sources: [paper PDF](pdfs/2024-confronting-reward-model-overoptimization-with-constrained-rlhf.pdf) · [detailed summary](summary/2024-confronting-reward-model-overoptimization-with-constrained-rlhf.md).

#### 3 October 2023 — Learning optimal advantage from preferences and mistaking it for reward

Catalog year: 2024; saved PDF version year: 2023.

**Problem:** What does preference learning estimate if people judge regret rather than accumulated reward?

**Approach:** Analyze the optimal-advantage interpretation and compare greedy action selection with reward-based optimization.

**Finding:** Under the regret model, preference learning estimates advantage rather than raw reward. Greedy maximization is simpler; incorrectly using advantage as reward can create looping or termination problems under approximation error.

Sources: [paper PDF](pdfs/2024-learning-optimal-advantage-from-preferences-and-mistaking-it-for-reward.pdf) · [detailed summary](summary/2024-learning-optimal-advantage-from-preferences-and-mistaking-it-for-reward.md).

#### 11 September 2023 — Open problems and fundamental limitations of reinforcement learning from human feedback

First preprint month: 2023-07.

**Problem:** Which RLHF failure modes can be patched, and which reflect deeper limitations of human feedback?

**Approach:** Survey problems in feedback collection, reward learning, and policy optimization.

**Finding:** Human approval does not reliably identify human goals; the survey motivates layered safeguards and auditing. It is a synthesis of existing evidence rather than a new benchmark result.

Sources: [paper PDF](pdfs/2023-open-problems-and-fundamental-limitations-of-reinforcement-learning-from-human-feedback.pdf) · [detailed summary](summary/2023-open-problems-and-fundamental-limitations-of-reinforcement-learning-from-human-feedback.md).

#### 7 September 2023 — Bootstrapping Adaptive Human-Machine Interfaces with Offline Reinforcement Learning

**Problem:** Can an adaptive interface infer intent and improve assistance from offline user-command data?

**Approach:** Use separate retrospective and online intent encoders, followed by human-in-the-loop adaptation.

**Finding:** ORBIT improves gaze-controlled simulated navigation in a 12-person study and several simulated control tasks. Physical assistive robotics and broad user generalization remain untested.

Sources: [paper PDF](pdfs/2023-bootstrapping-adaptive-human-machine-interfaces-with-offline-reinforcement-learning.pdf) · [detailed summary](summary/2023-bootstrapping-adaptive-human-machine-interfaces-with-offline-reinforcement-learning.md).

#### 19 July 2023 — Contextual reliability: When different features matter in different contexts

**Problem:** Should a model always ignore a feature labeled spurious in another setting?

**Approach:** Learn context-dependent feature relevance from limited annotations and enforce selective invariance.

**Finding:** ENP improves tested imitation and motion-forecasting robustness while approaching fully annotated classification baselines. Unseen-context generalization and closed-loop driving remain unestablished.

Sources: [paper PDF](pdfs/2023-contextual-reliability-when-different-features-matter-in-different-contexts.pdf) · [detailed summary](summary/2023-contextual-reliability-when-different-features-matter-in-different-contexts.md).

#### 8 March 2023 — Automatically auditing large language models via discrete optimization

**Problem:** How can undesirable language-model behavior be discovered systematically?

**Approach:** Jointly optimize discrete prompts and target outputs with autoregressive-consistency checks.

**Finding:** ARCA discovers toxicity and language switching and improves auditing success over tested methods. It needs white-box access, and failing to find an example does not certify safety.

Sources: [paper PDF](pdfs/2023-automatically-auditing-large-language-models-via-discrete-optimization.pdf) · [detailed summary](summary/2023-automatically-auditing-large-language-models-via-discrete-optimization.md).

#### 3 January 2023 — Benchmarks and algorithms for offline preference-based reward learning

**Problem:** Can fixed offline data support reward learning and new policies without collecting fresh transitions?

**Approach:** Actively query comparisons of existing trajectory snippets, learn rewards, and train offline RL.

**Finding:** OPRL produces new behavior combinations within existing transition support. The paper also finds common offline benchmarks can hide reward-learning failures because trivial rewards work surprisingly well.

Sources: [paper PDF](pdfs/2023-benchmarks-and-algorithms-for-offline-preference-based-reward-learning.pdf) · [detailed summary](summary/2023-benchmarks-and-algorithms-for-offline-preference-based-reward-learning.md).

#### 2 January 2023 — Towards modeling and influencing the dynamics of human learning

**Problem:** How should robot assistance change when people are still learning the task or interface?

**Approach:** Model changes in human beliefs about dynamics and goals, then optimize influence-aware shared control.

**Finding:** A 10-person Jaco-arm study improves measured action optimality but not perceived improvement significantly. Small, domain-specific human models limit broader conclusions.

Sources: [paper PDF](pdfs/2023-towards-modeling-and-influencing-the-dynamics-of-human-learning.pdf) · [detailed summary](summary/2023-towards-modeling-and-influencing-the-dynamics-of-human-learning.md).

#### 2023 year only — Learning to influence human behavior with offline reinforcement learning

**Problem:** Can an agent learn productive influence over human collaborators from existing interaction data?

**Approach:** Apply offline RL and history-conditioned partner modeling to human-human Overcooked gameplay.

**Finding:** The learned agents discover useful influence strategies and adapt to changing partners in separate experiments, outperforming tested baselines with real users. The setting is a game; the two capabilities are not unified in one complete physical system.

Sources: [paper PDF](pdfs/2023-learning-to-influence-human-behavior-with-offline-reinforcement-learning.pdf) · [detailed summary](summary/2023-learning-to-influence-human-behavior-with-offline-reinforcement-learning.md).

#### 2023 year only — Goal representations for instruction following: A semi-supervised language interface to control

**Problem:** Can a robot use unlabeled demonstrations while still following language instructions?

**Approach:** Contrastively align instructions with initial-to-goal visual transitions in GRIF.

**Finding:** Using 7,000 labeled and 47,000 unlabeled trajectories supports strong real-robot instruction following; the saved summary calculates 79.2% trial-weighted success versus 40.0% for adapted BC-Z. Evidence covers one platform and short instructions, not arbitrary long-horizon generalization.

Sources: [paper PDF](pdfs/2023-goal-representations-for-instruction-following-a-semi-supervised-language-interface-to-control.pdf) · [detailed summary](summary/2023-goal-representations-for-instruction-following-a-semi-supervised-language-interface-to-control.md).

#### 2023 year only — Learning representations that enable generalization in assistive tasks

**Problem:** Can an assistant adapt to a new person's behavior without knowing their reward?

**Approach:** Learn latent partner representations from interaction histories and adapt them with reward-free test-time observations.

**Finding:** PALM improves held-out-partner generalization in two simulated assistance tasks. It is not yet validated with real users or robots and lacks a fallback for adversarial partners.

Sources: [paper PDF](pdfs/2023-learning-representations-that-enable-generalization-in-assistive-tasks.pdf) · [detailed summary](summary/2023-learning-representations-that-enable-generalization-in-assistive-tasks.md).

## Main findings across the research

1. **Feedback quality is an identification problem.** Comparisons can omit why a person prefers a behavior, partial observation can reward appearances, and changing preferences complicate the objective itself. Richer language feedback and carefully selected queries improve some settings, but do not remove these underlying ambiguities.
2. **Human control can be trained as part of assistance.** Simulated empowerment, Minecraft assistance, and the coding user study show several ways to improve the person's contribution rather than only the assistant's autonomous task completion. Evidence is strongest within the evaluated tasks and interfaces.
3. **Representation structure can substitute for some explicit planning.** Goal-language alignment and temporal alignment support real-robot instruction following and composition of familiar behaviors. This remains constrained by the skills and transitions represented in training data.
4. **Stronger optimization can amplify the wrong target.** Reward hacking, approval manipulation, and engagement ranking show why higher proxy scores need not imply a better outcome for the user. These papers motivate constraints, more faithful objectives, and evaluations that look beyond approval alone.
5. **Monitoring is useful but incomplete.** Automatic audits and OOD monitors find additional failures. Missed behaviors, false alarms, and hidden reasoning prevent treating these tools as complete safety assurances.

## Open problems suggested by this work

The unresolved challenge is to combine useful adaptation, uncertainty about user goals, and reliable oversight in one system. Physical robots add limited demonstrations, contact risks, changing users, and perception errors. Language agents add opaque reasoning and strategic feedback gaming. The saved papers make progress on components of this problem, while most large-scale assistance and safety results still concern games, coding, conversations, or offline evaluation.

For an embodied-AI reader, the most direct starting points are GRIF for language grounding, TRA for compositional robot instructions, comparative-language feedback for personalized motion, RIGID for assistive stress testing, and ORBIT or PALM for adapting assistance to a person. Empower and AssistanceZero then provide broader formulations of preserving human control.

## Important catalog corrections

- The catalog's 2026 record **Active reward learning and iterative trajectory improvement from comparative language feedback** points to a PDF titled **Trajectory Improvement and Reward Learning from Comparative Language Feedback**, dated **8 October 2024**. Its demonstrated queries are random; active learning is future work in that version. The timeline uses the saved PDF's title and date.
- **Planning without Search** is cataloged as 2026, but the saved PDF is a **3 December 2025** version of a May 2025 preprint.
- **Temporal Representation Alignment** is cataloged as 2026, but its saved PDF is dated **13 February 2025**.
- Other differences between catalog years and preprint or revision dates may reflect conference publication versus preprint timing. They are shown beside the affected entries rather than silently changing the source manifests.
