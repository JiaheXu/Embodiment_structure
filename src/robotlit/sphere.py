"""Local topic navigation, deliberately separate from scientific match judgments."""
import hashlib
import re
from collections import Counter

from sqlalchemy import select

from .db import documents, papers, source_files, summaries

TOPICS = [
    ("dexterous", "Dexterous & tactile manipulation", "#54d5c3", ["dexterous", "dexterity", "in-hand", "tactile", "touch", "fingertip", "灵巧", "触觉"]),
    ("bimanual", "Bimanual manipulation", "#b5dd74", ["bimanual", "dual-arm", "two-arm", "双臂", "双手"]),
    ("vla", "Vision-language-action", "#f081b4", ["vision-language-action", "vla", "vision language action"]),
    ("world", "World & action models", "#f3a95c", ["world model", "world models", "world-action", "wam", "world modeling", "world prediction"]),
    ("objects", "Object-centric methods", "#d486f3", ["object-centric", "object centric", "object slots", "object tokens", "object graph"]),
    ("views", "Multi-view & camera geometry", "#6bacfa", ["multi-view", "multiview", "multi-camera", "camera pose", "camera poses", "extrinsics", "calibration", "view synthesis", "viewpoint"]),
    ("diffusion", "Diffusion & flow policies", "#8585ff", ["diffusion", "flow matching", "flow-matching", "flow policy"]),
    ("imitation", "Imitation & demonstrations", "#70bcf5", ["imitation", "behavior cloning", "behaviour cloning", "demonstration", "demonstrations", "teleoperation", "teleoperated"]),
    ("reinforcement", "Reinforcement learning", "#f09a78", ["reinforcement learning", "offline rl", "online rl", "rl", "mdp", "decision processes", "reward learning", "policy gradient", "policy gradients", "actor critic", "q learning", "value function", "value functions"]),
    ("planning", "Task & motion planning", "#8e9dfa", ["motion planning", "task planning", "planning", "trajectory optimization", "model predictive control", "trajectory prediction"]),
    ("transfer", "Sim-to-real & generalization", "#64b6f4", ["sim-to-real", "sim2real", "domain randomization", "generalization", "zero-shot"]),
    ("humanoid", "Humanoid & locomotion", "#f2b86d", ["humanoid", "humanoids", "locomotion", "legged", "quadruped", "whole-body", "walking", "bipedal", "parkour"]),
    ("mobile", "Navigation & mobile robotics", "#e4d668", ["mobile manipulation", "navigation", "mobile robot", "mobile robots", "mobile robotics", "slam", "traversability"]),
    ("language", "Vision & language models", "#c0bdf6", ["vision-language model", "vision-language models", "vision and language", "language model", "language models", "large language", "vlm", "vlms", "llm", "llms", "multimodal model", "multimodal models", "visual understanding", "captioning"]),
    ("contact", "Contact & force interaction", "#72d899", ["contact-rich", "force control", "impedance", "compliant", "contact dynamics", "contact exploration", "contact-aware"]),
    ("human_motion", "Human motion & pose", "#ea92b6", ["human pose", "human motion", "human body", "motion capture", "mocap", "skeleton", "hand pose", "human tracking"]),
    ("driving", "Autonomous driving", "#e7aa72", ["autonomous driving", "driving", "vehicle", "vehicles", "traffic", "autonomous car"]),
    ("aerial", "Aerial robotics", "#8acacc", ["aerial", "drone", "drones", "uav", "quadrotor", "quadrotors", "flight", "flying"]),
    ("reconstruction", "3D scenes & reconstruction", "#c4a3ef", ["reconstruction", "point cloud", "point clouds", "gaussian splatting", "3dgs", "nerf", "neural radiance", "3d representation", "3d scene", "4d", "depth estimation", "structure from motion", "geometric", "geometry", "spatial", "scene understanding", "occupancy", "mapping", "map learning"]),
    ("perception", "Perception & object understanding", "#77cde4", ["perception", "segmentation", "detection", "recognition", "tracking", "localization", "pose estimation", "image classification", "visual representation", "visual representations"]),
    ("generation", "Image, video & 3D generation", "#da8ee5", ["image generation", "video generation", "object generation", "world generation", "generative video", "text to image", "text to video", "image editing", "synthesis", "generative model", "generative models", "video prediction", "animation", "frame interpolation"]),
    ("interaction", "Human-robot interaction", "#e69bba", ["human robot", "robot human", "human in the loop", "human interaction", "interaction", "cooperation", "collaborative", "assistive", "assistance", "shared control", "brain computer", "rehabilitation", "wearable", "prosthetic"]),
    ("data", "Datasets, benchmarks & evaluation", "#b6ba72", ["dataset", "datasets", "benchmark", "benchmarks", "benchmarking", "bench", "evaluation", "evaluating", "data curation", "curating", "annotation", "annotations"]),
    ("safety", "Safety, uncertainty & recovery", "#ed978b", ["safety", "safe", "uncertainty", "failure", "failures", "recovery", "adversarial", "conformal", "collision avoidance", "anomaly"]),
    ("optimization", "Optimization & theory", "#afbbdf", ["optimization", "optimizer", "optimizers", "convergence", "regret", "solver", "solvers", "milp", "convex", "theorem", "theoretical", "stochastic processes", "quantum", "automata"]),
    ("reasoning", "Reasoning & agents", "#eca16f", ["reasoning", "agent", "agents", "agentic", "theory of mind", "cognition", "cognitive", "embodied reasoning", "symbolic"]),
    ("dynamics", "Control & system dynamics", "#7ac6a3", ["control", "controller", "controllers", "dynamics", "dynamical", "system identification", "stability", "stabilization", "optimal control", "kalman", "state estimation"]),
    ("manipulation", "Manipulation & grasping", "#a6d98b", ["manipulation", "grasp", "grasping", "gripper", "grippers", "pick and place", "assembly", "pushing", "deformable", "articulated", "object arrangement", "object fetching"]),
    ("learning", "Learning methods & representations", "#b4a4e9", ["representation learning", "representation", "representations", "contrastive", "self supervised", "pretraining", "pre training", "pretrained", "fine tuning", "finetuning", "distillation", "attention", "transformer", "transformers", "rnn", "rnns", "embedding", "embeddings", "features", "foundation model", "foundation models", "adaptation", "alignment", "neuron", "neurons", "machine learning", "neural networks", "tensor networks"]),
    ("systems", "Robot systems & deployment", "#8dbac5", ["deployment", "hardware", "latency", "real time", "realtime", "cloud robotics", "multi cloud", "distributed", "communication", "ros", "gpu", "gpus", "simulation", "simulator", "simulators", "robotic systems"]),
    ("ml_fundamentals", "ML fundamentals", "#a8b4ef", []),
    ("physics", "Nuclear & particle physics", "#e5c27a", []),
    ("healthcare", "Healthcare & medical applications", "#e7a6c9", []),
    ("cognition", "Cognitive science & neuroscience", "#c9a3df", []),
    ("education", "Education & learning technologies", "#a4ce95", []),
    ("patents", "Patents & technical inventions", "#c7b891", []),
    ("references", "Journal indexes & reference material", "#a8abb7", []),
    ("finance", "Finance & economics", "#d7c28a", []),
    ("materials", "Materials, chemistry & food science", "#b7cf90", []),
    ("energy", "Energy & electrical systems", "#e2b27c", []),
    ("software", "Software engineering", "#8abfc7", []),
    ("policy", "Policy learning", "#99d66a", ["policy learning", "robot learning", "robotic learning", "policy", "policies", "visuomotor", "generalist", "skill", "skills", "action prediction"]),
]


def normalized_words(text):
    return ' ' + ' '.join(re.findall(r'\w+', text.casefold())) + ' '


TOPIC_TERMS = {tid: list(dict.fromkeys(normalized_words(term) for term in terms)) for tid, _, _, terms in TOPICS}


def assign_topics(title, summary):
    category = re.search(r'^- \*\*Category ID:\*\*\s*(\w+)\s*$', summary, re.MULTILINE)
    if category and category[1] in TOPIC_TERMS:
        return {'group_id': category[1], 'topic_ids': [category[1]]}
    title, body = normalized_words(title), normalized_words(summary)
    scores = {}
    for tid, terms in TOPIC_TERMS.items():
        # Specific phrases outrank broad words; summary templates cannot swamp a title.
        title_score = sum(min(title.count(term), 2) * (1 + .4 * (len(term.split()) - 1)) for term in terms)
        if tid == 'data':
            title_score *= 1.5
        body_score = min(4, sum(min(body.count(term), 1) for term in terms))
        scores[tid] = title_score * 12 + body_score
    best = max(scores, key=scores.get)
    return {'group_id': best if scores[best] else 'other',
            'topic_ids': [tid for tid, score in scores.items() if score >= max(3, scores[best] * .65)] or ['other']}


def source_pdf_url(path):
    return '/v1/source-files/' + hashlib.sha256(str(path).encode()).hexdigest() + '/pdf'


def build_sphere(repo, sources=()):
    from .titles import paper_key
    with repo.engine.connect() as conn:
        docs = [dict(r) for r in conn.execute(select(documents, papers.c.title, papers.c.year)
                .join(papers, papers.c.paper_id == documents.c.paper_id)).mappings()]
        summary_rows = [dict(r) for r in conn.execute(select(summaries)).mappings()]
        source_aliases = {r['path']: dict(r) for r in conn.execute(select(source_files)).mappings()}
        aliases = {path: row['document_id'] for path, row in source_aliases.items()}
    nodes = {}
    source_ids = {}
    for doc in docs:
        nodes[doc['document_id']] = dict(id=doc['document_id'], document_id=doc['document_id'], paper_id=doc['paper_id'],
            title=doc['title'], year=doc['year'], summary='', summary_verified=False,
            source_url=f"/v1/documents/{doc['document_id']}/pdf", search_ready=bool(doc['active_generation_id']))
    for row in sorted(summary_rows, key=lambda r: r['path']):
        did = aliases.get(row['pdf_path']) or row['document_id']
        if did in nodes:
            nodes[did]['summary'] = row['text'][:5000]
            source_ids[row['pdf_path']] = did
            continue
        nid = 'summary-' + hashlib.sha256(row['path'].encode()).hexdigest()[:24]
        nodes[nid] = dict(id=nid, document_id=None, paper_id=None, title=row['title'], year=None,
                          summary=row['text'][:5000], summary_verified=False, source_url=None, search_ready=False)
        if row['pdf_path']:
            source_ids[row['pdf_path']] = nid
    for source in sources:
        path = str(source.path)
        alias = source_aliases.get(path)
        changed = alias is not None and (alias['size'], alias['mtime_ns']) != (source.size, source.mtime_ns)
        if not changed and aliases.get(path) in nodes:
            continue
        if not changed and path in source_ids:
            node = nodes[source_ids[path]]
            node['title'], node['year'] = source.title, source.year
            node['source_url'] = source_pdf_url(source.path)
            continue
        identity = f"{path}:{source.size}:{source.mtime_ns}" if changed else path
        nid = 'source-' + hashlib.sha256(identity.encode()).hexdigest()[:24]
        nodes[nid] = dict(id=nid, document_id=None, paper_id=None, title=source.title, year=source.year,
                         summary='', summary_verified=False, source_url=source_pdf_url(source.path), search_ready=False)
    counts = Counter()
    for node in nodes.values():
        node['paper_key'] = paper_key(node['title'])
        node.update(assign_topics(node['title'], node['summary']))
        counts[node['group_id']] += 1
    groups = [dict(id=tid, label=label, color=color, count=counts[tid]) for tid, label, color, _ in TOPICS if counts[tid]]
    if counts['other']:
        groups.append(dict(id='other', label='Other papers', color='#a080e8', count=counts['other']))
    return {'schema_version': '1.1', 'nodes': sorted(nodes.values(), key=lambda n: (n['title'].casefold(), n['id'])),
            'groups': groups, 'clustering': {'method': 'local title and summary topic terms', 'verified': False,
            'note': 'Topic proximity is a navigation hint, not evidence of scientific capability.'}}
