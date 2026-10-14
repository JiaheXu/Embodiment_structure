import sys
from types import ModuleType, SimpleNamespace


def test_docling_adapter_preserves_table_and_section_context(tmp_path,monkeypatch):
    from robotlit.parser import docling
    class Box:
        l,t,r,b = 10,20,90,80
        def to_top_left_origin(self, page_height): return self
    prov = SimpleNamespace(page_no=1,bbox=Box())
    label = lambda value: SimpleNamespace(value=value)
    header=SimpleNamespace(text='Evaluation',label=label('section_header'),level=1,prov=[prov])
    table=SimpleNamespace(label=label('table'),prov=[prov],model_dump=lambda mode:{'data':{'table_cells':[{'text':'85%','row':1,'col':1}]}},
                          export_to_markdown=lambda doc:'|Success|\n|85%|')
    doc=SimpleNamespace(export_to_dict=lambda:{'test':'structured'},pages={1:SimpleNamespace(size=SimpleNamespace(width=100,height=100))},
                        iterate_items=lambda:iter([(header,0),(table,1)]))
    module=ModuleType('docling.document_converter')
    module.DocumentConverter=lambda:SimpleNamespace(convert=lambda path:SimpleNamespace(document=doc))
    monkeypatch.setitem(sys.modules,'docling',ModuleType('docling'))
    monkeypatch.setitem(sys.modules,'docling.document_converter',module)
    result=docling(tmp_path/'synthetic.pdf',tmp_path/'parse.json')
    assert result['blocks'][1]['kind']=='table'
    assert result['blocks'][1]['structured']['data']['table_cells'][0]['text']=='85%'
    assert result['blocks'][1]['section']=='Evaluation'
    assert result['blocks'][1]['bbox']==[0.1,0.2,0.9,0.8]
