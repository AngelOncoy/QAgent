from uso import puede_comprar_alcohol, total_a_pagar


def test_total_con_veinte_por_ciento():
    assert total_a_pagar(100) == 80


def test_a_los_18_puede_comprar():
    assert puede_comprar_alcohol(18) is True
