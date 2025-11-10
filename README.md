# SMAT - Gemini Version

Ferramenta para identificação de conflitos semânticos em cenários de merge.

## Instruções rápidas

- Clone o repositório.
- Instale e configure o Java 8:

```bash
sudo apt update
sudo apt install openjdk-8-jdk
java -version  # Para verificar
```

- Instale as dependências do `requirements.txt`:

```bash
pip install -r SMAT/requirements.txt
```

- Altere o arquivo de configuração [`/SMAT/nimrod/tests/env-config.json`](/SMAT/nimrod/tests/env-config.json): atualize o campo `input_path` com o [caminho do arquivo de cenários](/input-smat.json) e configure a chave da API do Gemini em `api_params` (campo `api-key`).
  - Se não tiver uma chave, crie [acessando esse url com sua conta Google](https://aistudio.google.com/u/1/api-keys).

- Em `input-smat.json`, atualize os caminhos em `scenarioJars` para apontarem para os jars corretos no seu sistema.

- Para rodar o experimento use:

```bash
python3 run_experiment.py
```

# Atenção ao usar Windows
Se você usa o Windows como sistema operacional, ao clonar este projeto, provavelmente receberá uma mensagem de erro devido ao tamanho de alguns nomes de arquivos. Esse problema tornará impossível clonar este repositório.

Para resolver isso, você deve instalar o **Windows Subsystem for Linux (WSL)**; basta seguir as etapas descritas neste [guia](https://learn.microsoft.com/pt-br/windows/wsl/install). Ao final da instalação, abra o terminal Linux no seu Windows e clone o projeto normalmente.

Para executar o projeto, recomendamos o uso do **VSCode**, pois ele possui extensões que se integram ao WSL. Após instalar o WSL, ao abrir o VSCode, será exibida uma mensagem sugerindo o download da extensão **Remote - WSL**. Com essa extensão, é possível editar todos os arquivos que estão no WSL através do VSCode e executar o projeto pelo terminal.
