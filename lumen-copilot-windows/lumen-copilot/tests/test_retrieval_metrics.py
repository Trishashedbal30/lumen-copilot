from eval.run_eval import relevance_metrics

def test_retrieval_precision_recall_distinguish_multiple_relevant_pages():
    result=relevance_metrics(['wrong','a','b','other','last'],['a','b','missing'])
    assert result['precision@1']==0
    assert result['precision@5']==2/5
    assert result['relevant_page_recall@5']==2/3
    assert result['hit_rate@5']==1
    assert relevance_metrics([],['a'])['precision@5']==0
