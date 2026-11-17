import json
import pytest
from conta import Banco
from cliente import Cliente
from agencia import Agencia
from conta import Conta, ContaCorrente, ContaPoupanca, ContaSalario
from conta import Movimentacao
from dados_no_json import RepositorioJSON
from conta import ler_valor, brl
from cliente import cpf_valido
from app import criar_app


@pytest.fixture
def banco():
    banco = Banco('Banco de teste')
    banco.cadastrar_agencia('001', 'Centro', 'Aracaju')
    banco.cadastrar_agencia('002', 'Campus', 'São Cristóvão')
    return banco


def abrir(banco, cpf='52998224725', login='ana', tipo='corrente', codigo='001'):
    conta, mensagem = banco.abrir_conta('Ana Teste', cpf, codigo, login, '123', tipo)
    assert conta is not None, mensagem
    return conta


@pytest.fixture
def web(tmp_path):
    app = criar_app(str(tmp_path / 'dados.json'))
    app.config['TESTING'] = True
    return app, app.test_client()


def test_centavos_e_formatacao():
    assert ler_valor('10,50') == 1050
    assert ler_valor(' 0.01 ') == 1
    assert ler_valor('1,5') == 150
    assert ler_valor('0') == 0
    assert brl(123456789) == 'R$ 1.234.567,89'
    assert brl(-1) == '-R$ 0,01'
    for texto in ['', 'abc', '1.234', '1.000,00', '-1', '²', '1.', '.5']:
        assert ler_valor(texto) is None


def test_cpf():
    assert cpf_valido('52998224725')
    assert cpf_valido('11144477735')
    assert not cpf_valido('11111111111')
    assert not cpf_valido('52998224724')


def test_objetos_e_composicao(banco):
    conta = abrir(banco)
    assert isinstance(conta, Conta)
    assert isinstance(conta.cliente, Cliente)
    assert isinstance(conta.agencia, Agencia)
    assert conta.cliente is banco.buscar_cliente('529.982.247-25')
    assert conta.agencia is banco.buscar_agencia('001')
    assert conta.cliente.cpf_formatado() == '529.982.247-25'
    conta.depositar(100)
    assert isinstance(conta.consultar_extrato()[0], Movimentacao)


def test_heranca_e_polimorfismo(banco):
    corrente = abrir(banco)
    poupanca = abrir(banco, login='reserva', tipo='poupança')
    salario = abrir(banco, login='salario', tipo='salário')
    assert isinstance(corrente, ContaCorrente)
    assert isinstance(poupanca, ContaPoupanca)
    assert isinstance(salario, ContaSalario)
    descricoes = set()
    for conta in banco.listar_contas():
        assert isinstance(conta, Conta)
        assert conta.depositar(100)
        descricoes.add(conta.descricao_tipo())
    assert len(descricoes) == 3
    assert len(banco.listar_clientes()) == 1


def test_validacao_antes_de_cadastrar(banco):
    for nome, cpf, codigo, login, senha, tipo in [
        ('', '52998224725', '001', 'ana', 'x', 'corrente'),
        ('Ana', '11111111111', '001', 'ana', 'x', 'corrente'),
        ('Ana', '52998224725', '999', 'ana', 'x', 'corrente'),
        ('Ana', '52998224725', '001', '', 'x', 'corrente'),
        ('Ana', '52998224725', '001', 'ana', ' ', 'corrente'),
        ('Ana', '52998224725', '001', 'ana', 'x', 'outro')]:
        conta, mensagem = banco.abrir_conta(nome, cpf, codigo, login, senha, tipo)
        assert conta is None
        assert mensagem != ''
    assert banco.listar_contas() == []
    assert banco.listar_clientes() == []


def test_duplicidades_e_login(banco):
    abrir(banco)
    assert banco.cadastrar_cliente('Outra', '52998224725') is None
    assert banco.cadastrar_agencia('001', 'Repetida', 'Cidade') is None
    assert banco.cadastrar_agencia('003', '', 'Cidade') is None
    conta, mensagem = banco.abrir_conta('Bia', '11144477735', '001', 'ana', '123', 'corrente')
    assert conta is None
    assert banco.buscar_cliente('11144477735') is None
    assert banco.autenticar('ana', '123') is not None
    assert banco.autenticar('ana', 'errada') is None
    assert banco.autenticar('inexistente', '123') is None


def test_encapsulamento_listas(banco):
    conta = abrir(banco)
    conta.depositar(100)
    banco.listar_contas().clear()
    conta.consultar_extrato().clear()
    assert len(banco.listar_contas()) == 1
    assert len(conta.consultar_extrato()) == 1
    assert not hasattr(conta, 'saldo')
    assert not hasattr(conta, 'senha')
    assert conta.consultar_saldo() == 100


def test_depositar_sacar_e_saldo_exato(banco):
    conta = abrir(banco)
    assert conta.depositar(10)
    assert conta.depositar(20)
    assert conta.consultar_saldo() == 30
    assert conta.sacar(30)
    assert conta.consultar_saldo() == 0
    extrato = conta.consultar_extrato()
    assert len(extrato) == 3
    assert extrato[1].saldo_apos == 30
    assert extrato[-1].valor == -30
    assert conta.totais_movimentados() == (30, 30)


def test_operacoes_recusadas_nao_alteram_objetos(banco):
    a = abrir(banco)
    b = abrir(banco, cpf='11144477735', login='bia')
    a.depositar(1000)
    for valor in [0, -1, 1.5, True, None, '10']:
        assert not a.depositar(valor)
        assert not a.sacar(valor)
        assert not a.transferir(b, valor)
    assert not a.sacar(1001)
    assert not a.transferir(a, 10)
    assert not a.transferir(None, 10)
    assert not banco.transferir(a.numero, 999, 10)
    assert not banco.transferir(999, b.numero, 10)
    assert a.consultar_saldo() == 1000
    assert b.consultar_saldo() == 0
    assert len(a.consultar_extrato()) == 1
    assert b.consultar_extrato() == []


def test_transferencia_conserva_montante(banco):
    a = abrir(banco)
    b = abrir(banco, cpf='11144477735', login='bia', codigo='002')
    a.depositar(10000)
    assert banco.transferir(a.numero, b.numero, 3550)
    assert a.consultar_saldo() == 6450
    assert b.consultar_saldo() == 3550
    assert banco.montante_total() == 10000
    resumo = banco.resumo_agencias()
    assert resumo[0]['total'] == 6450
    assert resumo[1]['total'] == 3550
    assert resumo[0]['quantidade'] == 1
    assert a.consultar_extrato()[-1].valor == -3550
    assert b.consultar_extrato()[-1].valor == 3550


def test_filtro_cpf(banco):
    a = abrir(banco)
    b = abrir(banco, login='outra')
    abrir(banco, cpf='11144477735', login='bia')
    assert banco.listar_contas('529.982.247-25') == [a, b]
    assert banco.listar_contas('00000000000') == []


def test_json_restaura_classes_referencias_e_numero(banco, tmp_path):
    a = abrir(banco, tipo='poupança')
    b = abrir(banco, login='outra', tipo='salário')
    a.depositar(500)
    a.transferir(b, 125)
    repo = RepositorioJSON(str(tmp_path / 'dados.json'))
    repo.salvar(banco)
    novo = repo.carregar()
    assert isinstance(novo.buscar_conta(1), ContaPoupanca)
    assert isinstance(novo.buscar_conta(2), ContaSalario)
    assert novo.buscar_conta(1).cliente is novo.buscar_conta(2).cliente
    assert novo.buscar_conta(1).consultar_saldo() == 375
    assert len(novo.buscar_conta(1).consultar_extrato()) == 2
    assert novo.autenticar('ana', '123') is not None
    assert abrir(novo, login='terceira').numero == 3


def test_json_antigo_convertido_sem_perder_historico(tmp_path):
    caminho = tmp_path / 'antigo.json'
    dados = [[{'Nome': 'Ana', 'CPF': '52998224725'}],
             [{'Codigo da agencia': '001', 'Nome da agencia': 'Centro', 'Cidade': 'Aracaju'}],
             [{'numero': 20, 'cpf': '52998224725', 'codigo_agencia': '001', 'login': 'ana',
               'senha': '123', 'tipo': 'corrente', 'saldo': 10.5,
               'extrato': [{'data': '01/01/2026 10:00', 'tipo': 'DEPÓSITO',
                            'valor': 10.5, 'descricao': 'Depósito antigo'}]}]]
    caminho.write_text(json.dumps(dados), encoding='utf-8')
    repo = RepositorioJSON(str(caminho))
    banco = repo.carregar()
    a = banco.buscar_conta(20)
    assert a.consultar_saldo() == 1050
    assert a.consultar_extrato()[0].valor == 1050
    assert a.consultar_extrato()[0].data == '01/01/2026 10:00'
    assert abrir(banco, login='segunda').numero == 21
    repo.salvar(banco)
    assert json.loads(caminho.read_text())['versao'] == 2
    assert repo.carregar().buscar_conta(20).consultar_saldo() == 1050


def test_repositorio_ausente(tmp_path):
    banco = RepositorioJSON(str(tmp_path / 'novo.json')).carregar()
    assert banco.listar_contas() == []


def test_paginas_publicas_e_arquivos_estaticos(web):
    app, cliente = web
    for url in ['/', '/entrar', '/abrir-conta', '/admin/entrar', '/ajuda',
                '/static/style.css', '/static/Arasaka.png']:
        resposta = cliente.get(url)
        assert resposta.status_code == 200
        assert len(resposta.data) > 0
        resposta.close()
    for url in ['/painel', '/operacoes', '/extrato', '/admin',
                '/admin/agencias', '/admin/clientes', '/admin/contas']:
        assert cliente.get(url).status_code == 302


def test_fluxo_web_e_reabertura(web):
    app, cliente = web
    for nome, cpf, login in [('Ana', '52998224725', 'ana'), ('Bia', '11144477735', 'bia')]:
        resposta = cliente.post('/abrir-conta', data={'nome': nome, 'cpf': cpf,
            'codigo_agencia': '001', 'login': login, 'senha': '123', 'tipo': 'corrente'})
        assert resposta.status_code == 302
    cliente.post('/entrar', data={'login': 'ana', 'senha': '123'})
    assert cliente.get('/painel').status_code == 200
    cliente.post('/operacoes', data={'operacao': 'depositar', 'valor': '100,50'})
    cliente.post('/operacoes', data={'operacao': 'sacar', 'valor': '20', 'senha': '123'})
    cliente.post('/operacoes', data={'operacao': 'transferir', 'valor': '30,50',
                                    'senha': '123', 'destino': '2'})
    assert app.banco.buscar_conta(1).consultar_saldo() == 5000
    assert app.banco.buscar_conta(2).consultar_saldo() == 3050
    assert cliente.get('/operacoes').status_code == 200
    assert b'R$ 50,00' in cliente.get('/extrato').data
    novo = criar_app(app.repositorio.caminho)
    assert novo.banco.buscar_conta(1).consultar_saldo() == 5000
    cliente.get('/sair')
    assert cliente.get('/painel').status_code == 302


def test_senha_e_operacao_invalida_web(web):
    app, cliente = web
    a = abrir(app.banco)
    a.depositar(1000)
    cliente.post('/entrar', data={'login': 'ana', 'senha': '123'})
    cliente.post('/operacoes', data={'operacao': 'sacar', 'valor': '5', 'senha': 'errada'})
    cliente.post('/operacoes', data={'operacao': 'nao_existe', 'valor': '5'})
    cliente.post('/operacoes', data={'operacao': 'depositar', 'valor': '1,234'})
    assert a.consultar_saldo() == 1000
    assert len(a.consultar_extrato()) == 1


def test_filtro_extrato_web(web):
    app, cliente = web
    a = abrir(app.banco)
    a.depositar(2000)
    a.sacar(500)
    cliente.post('/entrar', data={'login': 'ana', 'senha': '123'})
    entradas = cliente.get('/extrato?tipo=entradas').data
    saidas = cliente.get('/extrato?tipo=saidas').data
    assert b'Dep\xc3\xb3sito na conta' in entradas
    assert b'Saque na conta' not in entradas
    assert b'Saque na conta' in saidas
    assert b'Dep\xc3\xb3sito na conta' not in saidas


def test_gerencia_e_filtro(web):
    app, cliente = web
    abrir(app.banco)
    abrir(app.banco, cpf='11144477735', login='bia')
    cliente.post('/admin/entrar', data={'senha': 'arasaka'})
    for url in ['/admin', '/admin/agencias', '/admin/clientes', '/admin/contas']:
        assert cliente.get(url).status_code == 200
    cliente.post('/admin/agencias', data={'codigo': '002', 'nome': 'Campus', 'cidade': 'Aracaju'})
    assert len(app.banco.listar_agencias()) == 2
    resposta = cliente.get('/admin/contas?cpf=52998224725')
    assert b'529.982.247-25' in resposta.data
    assert b'111.444.777-35' not in resposta.data


def test_sessao_admin_nao_e_sessao_cliente(web):
    app, cliente = web
    abrir(app.banco)
    cliente.post('/admin/entrar', data={'senha': 'arasaka'})
    assert cliente.get('/painel').status_code == 302
    cliente.post('/entrar', data={'login': 'ana', 'senha': '123'})
    assert cliente.get('/admin').status_code == 302


def test_modo_demo_e_persistencia(tmp_path):
    from main import criar_demo
    caminho = str(tmp_path / 'demo.json')
    app = criar_demo(caminho)
    assert len(app.banco.listar_contas()) == 3
    assert isinstance(app.banco.buscar_conta(1), ContaCorrente)
    assert isinstance(app.banco.buscar_conta(2), ContaPoupanca)
    assert isinstance(app.banco.buscar_conta(3), ContaSalario)
    assert app.banco.buscar_conta(1).consultar_saldo() == 228050
    assert app.banco.buscar_conta(2).consultar_saldo() == 12000
    assert app.banco.buscar_conta(3).consultar_saldo() == 150000
    outra = criar_demo(caminho)
    assert len(outra.banco.listar_contas()) == 3
    assert outra.banco.montante_total() == app.banco.montante_total()
