import pytest


@pytest.mark.parametrize('title,group', [
    ('Learning to Grasp Anything by Playing with Random Toys', 'manipulation'),
    ('Object Detection and Image Segmentation', 'perception'),
    ('Point Cloud Scene Reconstruction', 'reconstruction'),
    ('Iterative refinement improves compositional image generation', 'generation'),
    ('A Language Agent for Autonomous Driving', 'driving'),
    ('Open X-Embodiment: Robotic Learning Datasets and RT-X Models', 'data'),
    ('Visual Theory of Mind Enables Reasoning', 'reasoning'),
    ('Matrix-whitening optimizers for stochastic optimization', 'optimization'),
    ('Human-in-the-loop collaborative robotic assistance', 'interaction'),
    ('3D human pose estimation and motion capture', 'human_motion'),
    ('Diffusion policies for object manipulation', 'diffusion'),
    ('VISION–LANGUAGE MODELS for visual understanding', 'language'),
    ('A new camera-pose calibration method', 'views'),
])
def test_topic_registry_covers_actual_collection_gaps(title,group):
    from robotlit.sphere import assign_topics
    assert assign_topics(title,'')['group_id'] == group


def test_specific_title_wins_over_generic_summary_and_unknown_stays_other():
    from robotlit.sphere import assign_topics
    assert assign_topics('Bimanual dexterous hand control', 'Dataset benchmarks. Data, datasets, demonstration datasets and evaluation benchmarks.')['group_id'] == 'dexterous'
    assert assign_topics('Untitled research note', '')['group_id'] == 'other'


@pytest.mark.parametrize('category,title', [
    ('ml_fundamentals', 'Spectral collapse in continual learning'),
    ('physics', 'Flavor dependence of charged pion fragmentation functions'),
    ('systems', 'TorchRL: a library for PyTorch'),
])
def test_reviewed_summary_category_overrides_keyword_scoring(category, title):
    from robotlit.sphere import assign_topics
    summary = f'- **Category ID:** {category}\n\nDataset benchmarks and neural networks.'
    topics = assign_topics(title, summary)
    assert topics['group_id'] == category
    assert topics['topic_ids'] == [category]


def test_unknown_category_metadata_does_not_hide_paper():
    from robotlit.sphere import assign_topics
    assert assign_topics('Bimanual policy', '- **Category ID:** unknown-category')['group_id'] == 'bimanual'
