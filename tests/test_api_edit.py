
def test_wiki_edit_disabled(client):
    response = client.get("/wiki/artificial_intelligence/edit")
    assert response.status_code == 403
