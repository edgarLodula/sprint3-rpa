import sys

from src.db import test_connection
from src.monitor_eventos import verificar_anomalias

CATALOG_ROOT_URL = "https://www.weg.net/catalog/weg/BR/pt/Motores-El%C3%A9tricos/c/BR_MT"


def rodar_scraping_weg():
    # o import é feito aqui dentro e não lá em cima porque esses módulos já
    # abrem um Chrome assim que são importados, então só quer abrir quando
    # a pessoa realmente escolher essa opção
    from src.weg_page import pages
    pages(CATALOG_ROOT_URL)


def rodar_scraping_menzel():
    from src.menzel_page import run
    run()


def rodar_scraping_rsdelivers():
    from src.rsdelivers_page import run
    run()


def rodar_scraping_todos():
    """Roda as 3 fontes uma atrás da outra. Se uma falhar, as outras
    continuam mesmo assim."""
    for nome, funcao in [
        ("WEG", rodar_scraping_weg),
        ("MENZEL", rodar_scraping_menzel),
        ("RS DELIVERS", rodar_scraping_rsdelivers),
    ]:
        try:
            funcao()
        except Exception as e:
            print(f"[{nome}] Erro fatal, seguindo pras próximas fontes: {e}")


def menu_scraping():
    print("\n--- Web Scraping ---")
    print("1. WEG")
    print("2. Menzel")
    print("3. RS Delivers")
    print("4. Todos")
    print("0. Voltar")
    opcao = input("Escolha: ").strip()
    if opcao == "1":
        rodar_scraping_weg()
    elif opcao == "2":
        rodar_scraping_menzel()
    elif opcao == "3":
        rodar_scraping_rsdelivers()
    elif opcao == "4":
        rodar_scraping_todos()
    elif opcao == "0":
        return
    else:
        print("Opção inválida.")


def menu():
    print("\n=== Digital Twin - Sprint 3 ===")
    print("1. Testar conexão com banco (Pilar 2)")
    print("2. Web Scraping (Pilar 1)")
    print("3. Verificar anomalias e atualizar status (Pilar 2)")
    print("0. Sair")
    return input("Escolha: ").strip()


def main():
    while True:
        opcao = menu()
        if opcao == "1":
            test_connection()
        elif opcao == "2":
            menu_scraping()
        elif opcao == "3":
            verificar_anomalias()
        elif opcao == "0":
            sys.exit()
        else:
            print("Opção inválida.")


if __name__ == "__main__":
    main()
