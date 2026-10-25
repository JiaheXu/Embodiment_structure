# Negar Mehr and ICON Lab Research Overview

Updated 14 October 2026. Recent results appear first.

Negar Mehr's Intelligent Control lab studies how autonomous systems can interact safely and intelligently with humans and other robots. Across these papers, its central problem is **making learned and optimized robot behavior work in a shared world**: other agents have their own objectives, communication is imperfect, environments change, and task success must respect physical and safety constraints. The [ICON Lab](https://iconlab.negarmehr.com/) describes its foundations as control theory, game theory, robotics, and machine learning.

This overview uses the raw PDFs in this corrected folder, including methods, experiments, conclusions, and limitations. There are 39 catalog records representing 38 distinct readable source documents after recovering one malformed download. Dates below come from the saved PDF version, rather than assuming the filename year is its newest result. This is a chronology of available versions, not a claim that projects began in that order.

## Most recent results

| Saved PDF date | Work | Main finding |
| --- | --- | --- |
| 29 September 2026 | ALTER | A small residual coordination head adapts a frozen single-robot policy for teamwork while preserving individual skills. Simulated source-task success stays at 97.0–97.5% across the tested demonstration budgets. |
| 29 September 2026 | HuGo | An LLM writes and refines high-level humanoid policy code over an existing whole-body controller. Simulation and hardware support new task execution without task-specific demonstration collection or reward design; headline simulation comparisons use best-of-10 selection. |
| 26 September 2026 | SAMBAR | Replay-free continual VLA finetuning retains earlier skills while learning new ones. Hardware tests retain 100% on four pretraining tasks and reach 80% on each of two newly learned tasks. |
| 26 September 2026 | Hard constraints for hybrid systems | Locally affine safety buffers handle both continuous motion and dangerous state resets. The paper proves conditional safety and reports full constraint satisfaction in its pendulum and paddle-juggler tests. |
| 9 September 2026 | MIMIC-D | Decentralized diffusion policies learn compatible choices among multiple coordination modes, reducing collisions and supporting bimanual manipulation without explicit execution-time communication. |

Raw PDF sources: [ALTER](pdfs/2026-residual-denoising-enables-sample-efficient-multi-agent-coordination-on-demand.pdf), [HuGo](pdfs/2026-hugo-llms-as-whole-body-policy-code-designers-for-humanoid-loco-manipulation.pdf), [SAMBAR](pdfs/2026-sambar-selective-anchoring-via-method-of-multipliers-for-balanced-knowledge-acquisition-and-retention-in-vision-language.pdf), [hybrid safety](pdfs/2026-learning-control-policies-to-provably-satisfy-hard-affine-constraints-for-black-box-hybrid-dynamical-systems.pdf), and [MIMIC-D](pdfs/2026-mimic-d-multi-modal-imitation-for-multi-agent-coordination-with-decentralized-diffusion-policies.pdf).

## Main research topics and problems

**Strategic coordination among robots and people.** Multiple agents may be cooperative, competitive, or individually rational. The lab models interactions as dynamic games, finds multiple plausible equilibria, and learns decentralized policies. Its work asks both how to coordinate and when apparently good imitation remains exploitable.

**Safe learned control and physically feasible motion.** A high reward does not ensure that a robot avoids an unsafe state or follows its dynamics. POLICEd RL and its extensions design policy structure to enforce conditional hard constraints. DDAT constrains generated trajectories, while X-Safe corrects policy actions at runtime across embodiments.

**Learning what other agents know and want.** Human motion depends on intentions, incomplete perception, and responses to the robot. Inverse-game methods infer objectives; restricted-view models infer what an agent could observe; active learning chooses actions that make another agent's objective easier to distinguish.

**Distributed and continually updated scene maps.** A robot team needs consistent geometric knowledge despite asynchronous updates, packet loss, and environmental changes. Distributed NeRF, RAMEN, and UDON address agreement between robots; TACO addresses agreement with a robot's own past map while allowing outdated geometry to change.

**Reducing the human work needed to teach skills.** Adaptive teaching accounts for capability differences. CurricuLLM and CRAFT use foundation models to design curricula, rewards, or feedback. HuGo moves the model into direct high-level policy-code generation over a pretrained controller.

**Retaining skills while acquiring new ones.** SAMBAR and ALTER directly address forgetting during adaptation; TACO has the related mapping problem of preserving useful old information while revising stale information. These are related design goals with different algorithms and evidence.

**Scalable optimization and resource allocation.** Potential-game reductions and distributed planning make interactions computationally tractable. jaxipm accelerates batches of constrained robot optimization problems. Traffic and delivery papers study how control or prices can change selfish choices toward better network outcomes.

## How the research developed

The connections below synthesize the papers' problems and methods; they do not imply that every project forms one pipeline.

| Period | Direction | Research progression |
| --- | --- | --- |
| 2026 | Adaptable robot skills with explicit retention and safeguards | ALTER and SAMBAR preserve prior capabilities; HuGo generates executable task logic; MIMIC-D learns decentralized coordination. Hybrid safety, X-Safe, and GPU optimization address deployment constraints. |
| 2025 | Learned coaching and robust collaboration | CurricuLLM, LLM credit assignment, and CRAFT reduce manual task design. RAMEN handles asynchronous neural-map exchange, and DDAT makes generative motion more physically admissible. |
| 2024 | Uncertainty, perception, and multiple interaction modes | Human-view modeling and inverse crowd learning improve predictions; MultiNash-PF represents alternatives. Neural maps become distributed, and safety work replaces soft penalties with conditional hard constraints. |
| 2023 and earlier | Game-theoretic foundations and efficient planning | Maximum-entropy inverse games model interacting objectives; constrained potential games, RAPID, and distributed potential iLQR make strategic planning tractable. Teaching, assembly, and traffic studies extend the framework to distinct applications. |

## Research timeline with newest versions first

### 2026

#### 29 September 2026 — ALTER: Residual Denoising Enables Sample-Efficient Multi-Agent Coordination on Demand

**Problem:** Can an existing single-robot policy learn teamwork from little collaborative data while retaining its individual skills?

**Approach:** ALTER freezes the base diffusion policy and trains a residual coordination denoiser using collaborative demonstrations plus self-distilled single-arm rollouts.

**Findings and limits:** In the simulated place-and-wipe setting, combined source-task success remains 97.0–97.5% across the tested demonstration budgets; coordination also improves over the tested baselines. Hardware results support the same trade-off. Coordination is decentralized, but this is evidence for specific tasks and base policies rather than arbitrary robot teams.

Source: [raw PDF](pdfs/2026-residual-denoising-enables-sample-efficient-multi-agent-coordination-on-demand.pdf).

#### 29 September 2026 — HuGo: LLMs as Whole-Body Policy Code Designers for Humanoid Loco-Manipulation

**Problem:** Can a humanoid perform new locomotion-plus-manipulation tasks without collecting demonstrations or engineering a reward for each task?

**Approach:** HuGo uses an LLM to write closed-loop high-level policy code over a frozen whole-body controller, then refines the code from rollout trajectories and video frames.

**Findings and limits:** Across five simulated tasks and two low-level controllers, it outperforms the high-level RL baseline and approaches a demonstration-based baseline. It transfers policies to hardware and improves them using real rollouts. Reported headline comparisons use best-of-10 selection; difficult contact failures and the existing low-level controller's capabilities still constrain performance.

Source: [raw PDF](pdfs/2026-hugo-llms-as-whole-body-policy-code-designers-for-humanoid-loco-manipulation.pdf).

#### 26 September 2026 — SAMBAR: Selective Anchoring for VLA Knowledge Acquisition and Retention

**Problem:** How can a vision-language-action policy acquire new tasks without forgetting old tasks when old demonstrations are unavailable?

**Approach:** SAMBAR combines importance-weighted parameter anchoring with constrained optimization using the method of multipliers.

**Findings and limits:** Sequential LIBERO experiments retain 88.2% success on pretraining tasks and achieve 78.7% average success on three new tasks. Hardware experiments retain 100% on four old tasks and reach 80% on each of two new tasks. These finite evaluations support replay-free retention; they do not establish indefinite lifelong learning.

Source: [raw PDF](pdfs/2026-sambar-selective-anchoring-via-method-of-multipliers-for-balanced-knowledge-acquisition-and-retention-in-vision-language.pdf).

#### 26 September 2026 — Learning Control Policies to Provably Satisfy Hard Affine Constraints for Black-Box Hybrid Dynamical Systems

First preprint month: 2026-04.

**Problem:** Can learned control respect hard safety boundaries when unknown continuous dynamics also contain instantaneous state resets?

**Approach:** Use locally affine, repulsive policies near both the safety boundary and dangerous pre-reset states, with a switched actor elsewhere.

**Findings and limits:** The paper derives sufficient conditions and reports 100% constraint satisfaction in constrained-pendulum and paddle-juggler experiments. The guarantee assumes the stated conditions, including known affine reset maps. Choosing buffer widths and approximation bounds and extending to high-dimensional humanoids remain unresolved.

Source: [raw PDF](pdfs/2026-learning-control-policies-to-provably-satisfy-hard-affine-constraints-for-black-box-hybrid-dynamical-systems.pdf).

#### 9 September 2026 — MIMIC-D: Multi-modal Imitation for Multi-agent Coordination with Decentralized Diffusion Policies

First preprint month: 2025-09.

**Problem:** How can independently acting robots choose compatible strategies when several solutions are valid?

**Approach:** MIMIC-D jointly trains decentralized diffusion policies that learn coordination from local observations without explicit inter-agent messages at execution.

**Findings and limits:** Experiments demonstrate multiple coordination modes in navigation and bimanual lifting. In the two-agent swap evaluation, 15 of 100 sampled trajectories incur a collision, compared with 52 for vanilla diffusion. This improves empirical coordination; it does not prove collision-free operation, and local observations can include other agents' poses.

Source: [raw PDF](pdfs/2026-mimic-d-multi-modal-imitation-for-multi-agent-coordination-with-decentralized-diffusion-policies.pdf).

#### 3 July 2026 — Congestion Games with Heterogeneous Valuations: An Optimal Transport Approach

**Problem:** How should congested shared resources be allocated when users value different destinations differently?

**Approach:** Model heterogeneous destination valuations as a nonatomic congestion game and use optimal-transport duality to characterize equilibria and social optima.

**Findings and limits:** Both assignment problems admit finite-dimensional descriptions through thresholds, dual potentials, and aggregate flows. This is a theoretical reduction that can support computation; deployment-ready dynamic pricing mechanisms without knowledge of valuation distributions remain future work.

Source: [raw PDF](pdfs/2026-congestion-games-with-heterogeneous-valuations-an-optimal-transport-approach.pdf).

#### 24 June 2026 — Scaling Nonlinear Optimization: Many Problems One GPU

**Problem:** How can constrained nonlinear robot optimization exploit the throughput of GPU-batched learning systems?

**Approach:** jaxipm redesigns an IPOPT-style interior-point solver for JAX, using heterogeneous iteration fusion and iteration-level batching.

**Findings and limits:** Quadrotor optimization benchmarks show up to 32.85 times IPOPT's throughput with comparable solution quality. This measures many solves per second, not a universal reduction in individual control-loop latency. Larger problems reduce batching capacity and the speedup.

Source: [raw PDF](pdfs/2026-scaling-nonlinear-optimization-many-problems-one-gpu.pdf).

#### 21 June 2026 — Any-Body Guard: Universal Safeguarding for Manipulation Policies via Action Masking

**Problem:** Can one runtime safeguard prevent collisions across robot embodiments without retraining the task policy?

**Approach:** X-Safe builds probabilistically certified safe regions in configuration space and masks policy actions using forward kinematics and an object-based scene representation.

**Findings and limits:** Simulation and hardware experiments show cross-embodiment collision avoidance with less task degradation than the tested safeguards. Guarantees concern the modeled violation function and quasi-static setting. Dynamic humans and broader safety notions remain open, and hardware correction averages about 0.2 seconds per action with a 0.54-second worst case.

Source: [raw PDF](pdfs/2026-any-body-guard-universal-safeguarding-for-manipulation-policies-via-action-masking.pdf).

#### 5 June 2026 — CRAFT: Coaching Reinforcement Learning Autonomously Using Foundation Models for Multi-Robot Coordination

First preprint month: 2025-09; Catalog year: 2025; saved version year: 2026.

**Problem:** Can foundation models coach robots through long, difficult coordination tasks instead of requiring manual curricula and reward design?

**Approach:** CRAFT decomposes tasks with an LLM, generates subtask reward code, and refines rewards through VLM feedback on rollouts.

**Findings and limits:** Multi-quadruped navigation and bimanual experiments show learned coordination, with hardware transfer demonstrated for multi-quadruped navigation. Foundation-model variability can cause failed training attempts, so repeated simulation trials remain part of the practical method.

Source: [raw PDF](pdfs/2025-craft-coaching-reinforcement-learning-autonomously-using-foundation-models-for-multi-robot-coordination-tasks.pdf).

#### 28 May 2026 — TACO: Temporal Consensus Optimization for Continual Neural Mapping

First preprint month: 2026-02.

**Problem:** How can a robot update a neural map when objects move without replaying old observations that preserve outdated geometry?

**Approach:** TACO treats historical map snapshots as temporal neighbors and enforces importance-weighted consensus with reliable parts of previous models.

**Findings and limits:** Experiments revise moved geometry while preserving unchanged regions and reducing ghost artifacts. In the dynamic simulated comparison, F1 at 5 cm rises from 73.43 for MAS to 78.05 for TACO. Avoiding observation replay still requires storing model information, and weighting choices affect adaptation.

Source: [raw PDF](pdfs/2026-taco-temporal-consensus-optimization-for-continual-neural-mapping.pdf).

#### 19 March 2026 — UDON: Uncertainty-weighted Distributed Optimization for Multi-Robot Neural Implicit Mapping

First preprint month: 2025-09.

**Problem:** Can robots maintain consistent neural maps when almost all communication attempts fail?

**Approach:** UDON weights shared map information by uncertainty and uses distributed optimization that separately penalizes disagreement between communicating pairs.

**Findings and limits:** Dataset and hardware experiments maintain detailed reconstructions even with a tested communication success rate as low as 1%. This concerns successful exchanges, not a guarantee at arbitrarily low bandwidth or under permanent disconnection. Scaling to large environments through incrementally added submaps remains future work.

Source: [raw PDF](pdfs/2026-udon-uncertainty-weighted-distributed-optimization-for-multi-robot-neural-implicit-mapping-under-extreme-communication-c.pdf).

#### 24 February 2026 — Matching Multiple Experts: On the Exploitability of Multi-Agent Imitation Learning

**Problem:** Does accurately imitating multi-agent demonstrations guarantee a policy is difficult to exploit?

**Approach:** Analyze the Nash gap in Markov games and derive impossibility, hardness, and conditional upper-bound results.

**Findings and limits:** Even exact distribution matching need not yield a low-exploitability policy in general games. Dominant-strategy experts and best-response continuity permit useful bounds. This is an important theoretical limit on imitation objectives, not a demonstration that arbitrary cloned robot teams reach an equilibrium.

Source: [raw PDF](pdfs/2026-matching-multiple-experts-on-the-exploitability-of-multi-agent-imitation-learning.pdf).

### 2025

#### 10 August 2025 — Understanding and Imitating Human-Robot Motion with Restricted Visual Fields

First preprint month: 2024-10.

**Problem:** How can a robot explain and imitate human motion when people see only part of the scene?

**Approach:** Model field of view, viewing distance, and missed detections separately from the motion policy.

**Findings and limits:** A user study shows that explicitly modeling observation limitations improves learned navigation behavior; the policy also runs on a physical vehicle. The result depends on the studied perception model and environments, rather than assuming unrestricted access to a person's true observations.

Source: [raw PDF](pdfs/2025-understanding-and-imitating-human-robot-motion-with-restricted-visual-fields.pdf).

#### 10 August 2025 — MultiNash-PF: A particle filtering approach for computing multiple local generalized Nash equilibria in trajectory games

First preprint month: 2024-10.

**Problem:** How can a planner identify multiple plausible interaction outcomes quickly enough to respond to humans?

**Approach:** MultiNash-PF combines constrained potential trajectory games, implicit particle filtering, and local optimization refinement.

**Findings and limits:** Simulation reduces computation time by up to 50% relative to its baseline, and real human-robot interaction experiments demonstrate real-time responses to multiple modes. The algorithm finds local equilibria; it does not certify enumeration of all possible outcomes.

Source: [raw PDF](pdfs/2025-multinash-pf-a-particle-filtering-approach-for-computing-multiple-local-generalized-nash-equilibria-in-trajectory-games.pdf).

#### 31 May 2025 — When should a leader act suboptimally? The role of inferability in repeated Stackelberg games

First preprint month: 2023-10.

**Problem:** When should a robot accept a less optimal nominal strategy to make its behavior easier for a partner to infer?

**Approach:** Analyze repeated Stackelberg interactions in which a follower estimates a fixed mixed leader strategy from observed actions.

**Findings and limits:** The inferability gap depends on interaction count and strategy stochasticity; less random strategies can reduce the loss caused by difficult inference. Some near-optimal fully informed strategies have large inferability gaps. These are game-theoretic results under specified observation and interaction assumptions.

Source: [raw PDF](pdfs/2025-when-should-a-leader-act-suboptimally-the-role-of-inferability-in-repeated-stackelberg-games.pdf).

#### 26 April 2025 — RAMEN: Real-time Asynchronous Multi-agent Neural Implicit Mapping

First preprint month: 2025-02.

**Problem:** How can robots agree on neural maps while updates and communications occur asynchronously?

**Approach:** RAMEN uses uncertainty-weighted consensus ADMM and increases uncertainty for stale copies of neighbors' maps.

**Findings and limits:** Dataset and hardware evaluations show improved mapping under interrupted communication and different update frequencies. The method still relies on eventual information exchange and compatible map representations; performance in the experiments is not a guarantee under arbitrary outages.

Source: [raw PDF](pdfs/2025-ramen-real-time-asynchronous-multi-agent-neural-implicit-mapping.pdf).

#### 26 April 2025 — DDAT: Diffusion Policies Enforcing Dynamically Admissible Robot Trajectories

First preprint month: 2025-02.

**Problem:** How can a diffusion model generate motion that obeys a robot's dynamics rather than merely resembling demonstrations?

**Approach:** DDAT projects predicted trajectories onto approximations of reachable sets during training and inference.

**Findings and limits:** The paper demonstrates more dynamically admissible trajectories across simulated robots and hardware validation, supporting longer one-shot plans with less need to replan. The method still requires access to robot transition behavior and reachable-set approximation; admissibility is not a guarantee against every collision or environmental disturbance.

Source: [raw PDF](pdfs/2025-ddat-diffusion-policies-enforcing-dynamically-admissible-robot-trajectories.pdf).

#### 14 April 2025 — CurricuLLM: Automatic Task Curricula Design for Learning Complex Robot Skills

First preprint month: 2024-09.

**Problem:** Can language models automatically create a sequence of easier tasks that teaches a robot a difficult final skill?

**Approach:** CurricuLLM generates subtask descriptions, reward and goal-distribution code, and rollout-based evaluations for selecting policies to transfer onward.

**Findings and limits:** Experiments cover manipulation, navigation, and locomotion, and the paper validates a learned humanoid locomotion policy on hardware. Curriculum generation remains dependent on the environment interfaces and LLM evaluation; richer training-progress feedback is proposed for future work.

Source: [raw PDF](pdfs/2025-curricullm-automatic-task-curricula-design-for-learning-complex-robot-skills-using-large-language-models.pdf).

#### 26 March 2025 — Multi-agent inverse reinforcement learning in real world unstructured pedestrian crowds

First preprint month: 2024-05.

**Problem:** How can human objectives be inferred in dense crowds where people strongly influence one another's motion?

**Approach:** Use multi-agent maximum-entropy inverse reinforcement learning with a tractability-versus-rationality approximation and evaluate pedestrian datasets including Speedway.

**Findings and limits:** On the dense Speedway dataset, the paper reports the best result among seven comparison baselines and more than twice the performance of single-agent IRL under its evaluation. The evidence concerns interaction modeling and trajectory prediction, not a universal safety guarantee for crowd navigation. Record 31 contains the same PDF under an earlier title.

Source: [raw PDF](pdfs/2025-multi-agent-inverse-reinforcement-learning-in-real-world-unstructured-pedestrian-crowds.pdf).

#### 21 March 2025 — Strategic decision-making in multiagent domains: A weighted constrained potential dynamic game approach

First preprint month: 2023-08.

**Problem:** How can strategic robot interactions with coupled constraints be solved efficiently?

**Approach:** Identify weighted constrained potential-game structure so an equilibrium can be obtained through a single constrained optimal-control problem.

**Findings and limits:** Simulation shows faster solution than comparison game solvers, and two quadrotors carry a rigid object while avoiding two humans in hardware validation. The reduction depends on the required objective and constraint structure, rather than applying to every general-sum game.

Source: [raw PDF](pdfs/2025-strategic-decision-making-in-multiagent-domains-a-weighted-constrained-potential-dynamic-game-approach.pdf).

#### 24 February 2025 — Leveraging large language models for effective and explainable multi-agent credit assignment

**Problem:** How should a shared team reward be attributed to individual agents so they learn useful cooperation?

**Approach:** LLM-MCA uses a centralized language-model critic to decompose reward by contribution; LLM-TACA also assigns intermediate goals.

**Findings and limits:** The methods outperform comparison approaches in Level-Based Foraging, Robotic Warehouse, and Spaceworld simulations, and produce interpretable credit annotations. The evidence is benchmark-based, with the quality of the model's judgments and evaluation cost still relevant.

Source: [raw PDF](pdfs/2025-leveraging-large-language-models-for-effective-and-explainable-multi-agent-credit-assignment.pdf).

#### 24 February 2025 — ORASP: Optimal Robotic Assembly Sequence Planning

First preprint month: 2023-10; Catalog year: 2023; saved version year: 2025.

**Problem:** How can assembly order be optimized when possible sequences grow exponentially and feasibility constraints must be respected?

**Approach:** ORASP formulates sequencing as an MDP and shortest-path problem, using dynamic programming, graph exploration, and deep RL for larger cases.

**Findings and limits:** The reported assembly-planning benchmarks improve speed and scalability over comparison methods, including large space-structure examples. Graph-state growth remains exponential, and the result is about planning sequences rather than demonstrating autonomous physical assembly of those structures.

Source: [raw PDF](pdfs/2023-optimal-robotic-assembly-sequence-planning-a-sequential-decision-making-approach.pdf).

### 2024

#### 23 December 2024 — Risk-Sensitive Orbital Debris Collision Avoidance Using Distributionally Robust Chance Constraints

Catalog year: 2025; saved version year: 2024.

**Problem:** How can satellites avoid debris with an interpretable probability limit when uncertainty is non-Gaussian or incompletely known?

**Approach:** Approximate chance constraints with distributionally robust conditional-value-at-risk constraints using moment information, within MPC solved by cross-entropy sampling.

**Findings and limits:** The real-world-inspired orbital simulations avoid collisions under the tested uncertainty scenarios while balancing maneuver cost. The results validate the formulation in simulation; they are not flight deployment, and the approximation can be conservative.

Source: [raw PDF](pdfs/2025-risk-sensitive-orbital-debris-collision-avoidance-using-distributionally-robust-chance-constraints.pdf).

#### 21 November 2024 — To what extent do open-loop and feedback Nash equilibria diverge in general-sum linear quadratic dynamic games?

First preprint month: 2024-09.

**Problem:** When is a cheaper open-loop game solution a reasonable substitute for feedback interaction planning?

**Approach:** Construct an auxiliary linear-quadratic game with perturbed costs and compare its Riccati solutions with those of the original game.

**Findings and limits:** The paper gives conditions for open-loop and feedback Nash equilibria to coincide and bounds their divergence. This supplies a principled solver-selection criterion within the studied linear-quadratic class, not an equivalence for nonlinear games generally.

Source: [raw PDF](pdfs/2024-to-what-extent-do-open-loop-and-feedback-nash-equilibria-diverge-in-general-sum-linear-quadratic-dynamic-games.pdf).

#### 15 November 2024 — Pricing for Multi-modal Pickup and Delivery Problems with Heterogeneous Users

First preprint month: 2023-03.

**Problem:** How should a delivery service price multiple modes when users trade off price and latency differently?

**Approach:** Construct a congestion game on a star network and derive prices that implement desired feasible delivery flows.

**Findings and limits:** The network structure gives a closed-form pricing solution, with a meal-delivery case study using real-world data. The guarantee relies on the specified choice model and network geometry, rather than arbitrary logistics networks.

Source: [raw PDF](pdfs/2024-pricing-for-multi-modal-pickup-and-delivery-problems-with-heterogeneous.pdf).

#### 5 November 2024 — POLICEd RL: Learning Closed-Loop Robot Control Policies with Provable Satisfaction of Hard Constraints

First preprint month: 2024-03.

**Problem:** Can a learned policy enforce a hard boundary instead of merely being penalized for crossing it?

**Approach:** POLICEd RL forces the policy to be affine in a repulsive buffer around an unsafe set.

**Findings and limits:** The paper derives conditions for safe policies and shows hard-constraint enforcement in robotic experiments. Training is not guaranteed to converge to such a policy, and checking buffer vertices scales poorly with dimension. The safety result is conditional on obtaining and verifying the required policy.

Source: [raw PDF](pdfs/2024-policed-rl-learning-closed-loop-robot-control-policies-with-provable-satisfaction-of-hard-constraints.pdf).

#### 11 October 2024 — Active inverse learning in stackelberg trajectory games

First preprint month: 2023-08; Catalog year: 2025; saved version year: 2024.

**Problem:** Can an agent learn another agent's objective faster by choosing informative actions rather than passively watching?

**Approach:** In a Stackelberg trajectory game, optimize leader controls to separate the follower's responses under a finite set of objective hypotheses.

**Findings and limits:** The optimized inputs accelerate hypothesis-probability convergence compared with uniformly random inputs in virtual TurtleBot experiments. The result assumes a candidate hypothesis set and uses simulation, rather than identifying arbitrary human goals on hardware.

Source: [raw PDF](pdfs/2025-active-inverse-learning-in-stackelberg-trajectory-games.pdf).

#### 30 September 2024 — Distributed nerf learning for collaborative multi-robot perception

**Problem:** Can a team build one scene representation while sharing learned models instead of all raw camera observations?

**Approach:** Learn local NeRF models from posed RGB images and bring their parameters into distributed consensus.

**Findings and limits:** Real-scene dataset experiments approach centralized mapping quality and sometimes improve sparse-view geometry through regularization. This is a foundation for collaborative perception, with camera poses and a compatible scene-model architecture provided.

Source: [raw PDF](pdfs/2024-distributed-nerf-learning-for-collaborative-multi-robot-perception.pdf).

#### 29 July 2024 — Learning to provably satisfy high relative degree constraints for black-box systems

**Problem:** Can learned policies keep a safety constraint when the control input affects it only after a delay through the dynamics?

**Approach:** Extend locally affine repulsive buffers to dissipate inertia for high-relative-degree affine constraints.

**Findings and limits:** The paper proves deterministic closed-loop constraint satisfaction under its conditions and demonstrates inverted-pendulum and shuttle-landing simulations. It extends the scope of POLICEd RL, with guarantees tied to the assumed system regularity and successfully obtained policy.

Source: [raw PDF](pdfs/2024-learning-to-provably-satisfy-high-relative-degree-constraints-for-black-box-systems.pdf).

#### 23 May 2024 — Adaptive teaching in heterogeneous agents: Balancing surprise in sparse reward scenarios

**Problem:** How can a teacher demonstrate useful behavior when a student has weaker actuators or different constraints?

**Approach:** Adapt teacher behavior to reduce the student's surprise at demonstrations while maintaining the teacher's exploration surprise.

**Findings and limits:** Sparse-reward control experiments show better student learning when capabilities differ. The result concerns simulated teacher-student tasks, rather than a general solution for transfer between arbitrary robot morphologies.

Source: [raw PDF](pdfs/2024-adaptive-teaching-in-heterogeneous-agents-balancing-surprise-in-sparse-reward-scenarios.pdf).

#### 8 March 2024 — Integrating predictive motion uncertainties with distributionally robust risk-aware control for safe robot navigation in crowds

**Problem:** How can uncertain human-motion predictions be used in a safety-aware robot control loop?

**Approach:** Use distributionally robust chance-constrained MPC with a conservative CVaR approximation and parallel sampling optimization.

**Findings and limits:** Case studies based on real pedestrian trajectories support real-time, risk-aware navigation. Safety statements depend on the uncertainty description and constraint assumptions; real-world pedestrian data is not itself a physical human-robot deployment experiment.

Source: [raw PDF](pdfs/2024-integrating-predictive-motion-uncertainties-with-distributionally-robust-risk-aware-control-for-safe-robot-navigation-in.pdf).

#### 7 March 2024 — Weathering ongoing uncertainty: Learning and planning in a time-varying partially observable environment

First preprint month: 2023-12.

**Problem:** How should a robot learn and plan when both environment dynamics and its observations change over time?

**Approach:** Model a time-varying POMDP and use memory-prioritized state estimation with a corresponding planning strategy.

**Findings and limits:** Simulation and robot hardware tests improve on standard methods in the studied changing environments. The framework addresses nonstationary uncertainty; it does not remove dependence on state estimation and the specified temporal model.

Source: [raw PDF](pdfs/2024-weathering-ongoing-uncertainty-learning-and-planning-in-a-time-varying-partially-observable-environment.pdf).

### 2023

#### 4 August 2023 — Efficient constrained multi-agent trajectory optimization using dynamic potential games

First preprint month: 2022-06.

**Problem:** Can coupled multi-agent trajectory constraints be solved without optimizing a separate control problem for every agent?

**Approach:** Exploit constrained dynamic potential-game structure to solve for a generalized Nash equilibrium through one constrained optimization problem.

**Findings and limits:** A four-planar-agent navigation comparison is about 20 times faster on average than the tested state-of-the-art solver. Quadrotor object-transport experiments supply hardware validation. The method relies on potential-game structure and targets constrained equilibrium planning.

Source: [raw PDF](pdfs/2023-efficient-constrained-multi-agent-trajectory-optimization-using-dynamic-potential-games.pdf).

#### 30 April 2023 — RAPID: Autonomous Multi-agent Racing Using Constrained Potential Dynamic Games

First preprint month: 2023-05.

**Problem:** How can autonomous racers respond strategically to one another in real time?

**Approach:** RAPID expresses multi-agent racing as a constrained dynamic potential game and solves one associated optimal-control problem.

**Findings and limits:** Simulation outperforms the comparison approach and hardware experiments demonstrate real-time capability. This establishes feasibility for the tested racing interaction model, not universal optimality against arbitrary competitors.

Source: [raw PDF](pdfs/2023-rapid-autonomous-multi-agent-racing-using-constrained-potential-dynamic-games.pdf).

#### 8 March 2023 — Distributed potential ilqr: Scalable game-theoretic trajectory planning for multi-agent interactions

**Problem:** How can game-theoretic motion planning scale beyond a centralized solver?

**Approach:** Distributed potential iLQR minimizes a shared potential through distributed trajectory optimization.

**Findings and limits:** Simulation and multi-quadrotor experiments improve efficiency and scalability over the centralized comparison. Consistency and synchronization between local plans remain relevant limitations, and the approach assumes compatible potential-game structure.

Source: [raw PDF](pdfs/2023-distributed-potential-ilqr-scalable-game-theoretic-trajectory-planning-for-multi-agent-interactions.pdf).

#### 7 March 2023 — Learning to Influence Vehicles' Routing in Mixed-Autonomy Networks by Dynamically Controlling the Headway of Autonomous Cars

**Problem:** Can controlling autonomous-car headway improve network traffic rather than merely increasing local road capacity?

**Approach:** Train an RL policy that adjusts headways and therefore link capacities while modeling human route-choice adaptation.

**Findings and limits:** Simulated mixed-autonomy networks show how headway control can improve travel-time outcomes and avoid adverse routing responses. The result is a network-control study; it is not a deployed rule for changing headway in live traffic.

Source: [raw PDF](pdfs/2023-learning-to-influence-vehicles-routing-in-mixed-autonomy-networks-by-dynamically-controlling-the-headway-of-autonomous-c.pdf).

#### 2023 year only — Adaptive learning from demonstration in heterogeneous agents: Concurrent minimization and maximization of surprise in sparse reward environments

Document type: Emma Clark's master's thesis, advised by Negar Mehr.

**Problem:** How can demonstration learning accommodate a student whose dynamics differ from the teacher's?

**Approach:** Emma Clark's master's thesis, advised by Negar Mehr, develops simultaneous teacher and student learning using exploration surprise and student compatibility.

**Findings and limits:** MountainCar, CartPole, and HalfCheetah experiments support capability-aware teaching. This is a supervised thesis and precursor to the later adaptive-teaching paper, not an independent deployment of human-to-robot transfer.

Source: [raw PDF](pdfs/2023-adaptive-learning-from-demonstration-in-heterogeneous-agents-concurrent-minimization-and-maximization-of-surprise-in-spa.pdf).

### 2021

#### 3 October 2021 — Maximum-Entropy Multi-Agent Dynamic Games: Forward and Inverse Solutions

Catalog year: 2023; saved version year: 2021.

**Problem:** How can interacting agents' uncertain behavior and objectives be modeled instead of treating each agent as an isolated optimizer?

**Approach:** The recovered 2021 preprint defines Entropic Cost Equilibrium, derives forward policies, and learns agents' costs from noisy trajectories through inverse dynamic games.

**Findings and limits:** Simulation and the INTERACTION traffic dataset support more accurate cost inference than comparison inverse-optimal-control methods. Closed-form results apply to the linear-quadratic-Gaussian case, with local approximations for nonlinear games. This PDF is an earlier preprint, not the unreadable 2023 journal file.

Source: [raw PDF](pdfs/2023-maximum-entropy-multi-agent-dynamic-games-forward-and-inverse-solutions-arxiv.pdf).

## What the lab has established across these papers

1. **Interaction structure can make strategic planning tractable.** Potential-game assumptions reduce some coupled-agent planning problems to one optimization problem. Distributed variants improve scaling, and particle-filter methods expose multiple local solutions. These advantages depend on the modeled structure.
2. **Learning coordination requires compatible choices.** Averaging demonstrations across different valid modes can fail. MIMIC-D learns decentralized multimodal behavior, while the exploitability paper shows that imitation accuracy alone cannot generally guarantee strategic robustness.
3. **Safety requires specifying and verifying the constraint.** Repulsive policy buffers and action masks support formal claims under stated assumptions. They address different hazards: affine state boundaries, hybrid reset jumps, or geometric collisions. These guarantees should not be merged into an unrestricted claim of safe autonomy.
4. **Past information needs selective trust.** Stale shared maps, moved objects, and forgotten skills all reveal the tension between retention and adaptation. Uncertainty weighting, temporal consensus, selective anchoring, and residual adaptation provide distinct ways to manage it.
5. **Foundation models can reduce task-design effort.** Curricula, reward critics, coaching, and policy code help acquire skills with less manual specification. Existing controllers, simulation trials, code interfaces, and evaluation still carry substantial work.

## Open research questions

Can these components be combined into one robot team that keeps learning, coordinates with unfamiliar people, and has useful safety guarantees under changing perception and communication? The papers establish parts of this goal, with different assumptions and evaluation settings. Robustness to dynamic humans, scalable verification, broad partner generalization, and long-term retention remain important gaps.

A concrete emerging direction is to adapt pretrained skills instead of learning every task from scratch, preserve previous capabilities during that adaptation, and constrain the resulting behavior through geometry or control structure. This interpretation connects ALTER, SAMBAR, HuGo, and the safety papers; it is a synthesis of the research, rather than a claim that the lab has already built that combined system.

## Source and chronology notes

- **Duplicate:** The catalog entries “Multi-agent inverse reinforcement learning in real world unstructured pedestrian crowds” and “Towards imitation learning in real world unstructured social mini-games in pedestrian crowds” contain byte-identical PDFs of arXiv:2405.16439v3. They are summarized once.
- **Recovered source:** The original file named `2023-maximum-entropy-multi-agent-dynamic-games-forward-and-inverse-solutions.pdf` contains an HTML error page. A valid raw arXiv PDF was saved separately with the suffix `-arxiv.pdf`. Its banner identifies the 3 October 2021 preprint, so the overview describes that version rather than claiming to have read the later journal article. The original file remains unchanged.
- **Version dates:** Several filename years differ from the date on the actual PDF. CRAFT's saved version is from June 2026 despite a 2025 filename; ORASP's is from February 2025 despite a 2023 filename. These dates reflect revision history as well as first release, and catalog years are retained beside affected entries.
- **Attribution:** The raw documents name Negar Mehr as author or, for the master's thesis, adviser. Findings above come from these PDFs, rather than existing generated paper summaries. The official lab site supplies only institutional context.
