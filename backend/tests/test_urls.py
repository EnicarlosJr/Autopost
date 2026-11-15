from app.products.urls import normalize_product_url

def test_tracking_parameters_and_fragment_are_removed():
    a = normalize_product_url("https://Produto.MercadoLivre.com.br/MLB-123-tenis/?utm_source=x&matt_tool=1#polycard")
    b = normalize_product_url("https://produto.mercadolivre.com.br/MLB-123-tenis")
    assert a == b

def test_meaningful_parameters_are_kept():
    assert "id=9" in normalize_product_url("https://loja.example/p?id=9&utm_medium=social")
