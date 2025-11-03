# Servidor Gateway Poliglota para Rastreamento Veicular

Este projeto é um **gateway de tradução universal** para o setor de telemétria, projetado para resolver o desafio da **fragmentação de protocolos**. Com uma arquitetura modular e de alto desempenho, ele atua como uma ponte entre diversos modelos de rastreadores e uma plataforma central.

## Tabela de Conteúdos
- [Visão Geral](#visão-geral)
- [Principais Funcionalidades](#principais-funcionalidades)
- [Arquitetura do Sistema](#arquitetura-do-sistema)
  - [Fluxo de Dados (Uplink)](#fluxo-de-dados-uplink-dispositivo---plataforma)
  - [Fluxo de Comandos (Downlink)](#fluxo-de-comandos-downlink-plataforma---dispositivo)
- [Dados Persistidos no Redis](#dados-persistidos-no-redis)
- [Gerenciamento de Sessões TCP](#gerenciamento-de-sessões-tcp)
- [Gerenciamento de Rastreadores Híbridos (GSM/Satélite)](#gerenciamento-de-rastreadores-híbridos-gsm-satélite)
- [Rastreabilidade de Logs Aprimorada](#rastreabilidade-de-logs-aprimorada)
- [Streaming de Logs em Tempo Real (WebSocket)](#streaming-de-logs-em-tempo-real-websocket)
- [Protocolos Suportados](#protocolos-suportados)
- [Endpoints da API](#endpoints-da-api)
- [Como Começar](#como-começar)
- [Como Adicionar um Novo Protocolo](#como-adicionar-um-novo-protocolo)
- [Estrutura do Projeto (Árvore de Diretórios)](#estrutura-do-projeto)
- [Tecnologias Utilizadas](#tecnologias-utilizadas)

## Visão Geral

A força deste projeto reside em sua arquitetura inteligente e desacoplada, que oferece funcionalidades muito além de uma simples tradução de dados. Ele foi desenhado para ser uma solução "plug-and-play", onde adicionar suporte a novos protocolos de entrada ou saída exige o mínimo de esforço, sem impactar a estabilidade do sistema existente. O objetivo é fornecer uma base robusta e flexível para qualquer plataforma de rastreamento.

## Principais Funcionalidades

*   **Arquitetura Modular "Plug-and-Play"**: Adicionar suporte a um novo protocolo é tão simples quanto criar um novo módulo. A estrutura isola a lógica de cada protocolo, permitindo que o sistema evolua sem aumento de complexidade. O orquestrador em [`main.py`](main.py) carrega dinamicamente cada protocolo, iniciando listeners dedicados em threads separadas.

*   **Tradução Bidirecional (N x N)**: O sistema traduz múltiplos protocolos de entrada para múltiplos protocolos de saída. Cada `mapper` de entrada converte o dialeto do dispositivo para um **dicionário Python padronizado**. A camada de `output` (ex: [`app/src/output/suntech4g/builder.py`](app/src/output/suntech4g/builder.py)) utiliza esse dicionário para construir pacotes nos formatos de saída desejados, garantindo um desacoplamento total.

*   **Inteligência Agregada com Gestão de Estado**: O gateway utiliza o Redis ([`app/services/redis_service.py`](app/services/redis_service.py)) para armazenar o estado de cada dispositivo. Ao receber um novo pacote, ele compara o estado atual com o anterior e pode **gerar novos eventos de alerta** (ex: "Alerta de Ignição Ligada") que não existiam no protocolo original, agregando valor e inteligência aos dados.

*   **Roteamento Reverso de Comandos**: O fluxo de comandos (downlink) é igualmente robusto. Comandos recebidos pela plataforma são traduzidos por um `mapper` de saída (ex: [`app/src/output/suntech4g/mapper.py`](app/src/output/suntech4g/mapper.py)) para um formato universal. O sistema então identifica o protocolo de origem do dispositivo e invoca o `builder` correspondente (ex: [`app/src/input/j16x_j16/builder.py`](app/src/input/j16x_j16/builder.py)) para enviar o comando no formato nativo do rastreador.

*   **Logs Contextualizados e Rastreáveis**: O sistema de log foi aprimorado para incluir um `log_label` em cada registro. Utilizando `logger.contextualize`, cada thread de comunicação de um rastreador é "marcada" com sua identidade, garantindo que todas as operações subsequentes, de qualquer função ou módulo, sejam registradas com o ID correto. Isso simplifica drasticamente a depuração e o monitoramento de dispositivos específicos em um ambiente de alta concorrência.

*   **Streaming de Logs em Tempo Real via WebSocket**: Para facilitar a depuração e o monitoramento ao vivo, foi implementado um servidor WebSocket ([`app/websocket/ws.py`](app/websocket/ws.py)). Clientes podem se conectar a este servidor para receber um fluxo contínuo de logs filtrados por um `log_label` específico, permitindo uma análise detalhada do comportamento de um dispositivo em tempo real.

## Arquitetura do Sistema

A arquitetura foi desenhada para máxima clareza, escalabilidade e manutenibilidade. A seguir, os fluxos de dados e comandos são detalhados para ilustrar o funcionamento interno do gateway.

### Fluxo de Dados (Uplink: Dispositivo -> Plataforma)

Este diagrama mostra como os dados de um rastreador são recebidos, traduzidos e encaminhados para a plataforma final.

```mermaid
graph TD
    A[Dispositivo Rastreador] -- Pacote TCP --> B(Listener de Protocolo de Entrada);
    B -- Bytes Brutos --> C{Handler};
    C -- Pacote Bruto --> D(Processor);
    D -- Dados Dissecados --> E(Input Mapper);
    E -- Dicionário Padrão --> F(send_to_main_server);
    F -- Dicionário Padrão --> G{Output Builder};
    G -- Pacote de Saída Formatado --> H(Main Server Connection);
    H -- Pacote TCP --> I[Plataforma Principal];

    subgraph "Módulo de Protocolo de Entrada (Ex: j16x_j16, vl01)"
        C
        D
        E
    end

    subgraph "Módulo de Protocolo de Saída (Ex: Suntech4G, GT06)"
        G
    end

    subgraph "Serviços Centrais"
        F
        H
    end
```

### Fluxo de Comandos (Downlink: Plataforma -> Dispositivo)

Este diagrama ilustra como os comandos são enviados da plataforma de volta para o dispositivo correto, na linguagem correta.

```mermaid
graph TD
    A[Plataforma Principal] -- Pacote TCP --> B(Main Server Connection);
    B -- Bytes Brutos --> C{Output Mapper};
    C -- Comando Universal --> D(Roteador de Comandos);
    D -- Consulta Protocolo de Entrada (DevID) --> E{Redis};
    E -- Retorna Protocolo (ex: 'j16x_j16') --> D;
    D -- Comando Universal para Builder Específico --> F{Input Builder};
    F -- Pacote Binário Nativo --> G(Socket do Dispositivo);
    G -- Pacote TCP --> H[Dispositivo Rastreador];

    subgraph "Módulo de Protocolo de Saída (Ex: Suntech4G, GT06)"
        C
    end

    subgraph "Módulo de Protocolo de Entrada (Ex: j16x_j16, vl01)"
        F
    end

    subgraph "Serviços Centrais"
        B
        D
        E
    end
```

## Dados Persistidos no Redis

O Redis é utilizado como um armazenamento de estado de curto prazo e cache para otimizar as operações do gateway. As chaves são categorizadas principalmente por `device_id` (IMEI) para dados do rastreador e chaves `history:<device_id>` para o histórico de pacotes.

### Estrutura de Dados do Dispositivo (`<device_id>`)

Para cada rastreador conectado ou que já se conectou, um hash é mantido no Redis sob a chave sendo o `device_id` (geralmente o IMEI em formato hexadecimal ou string, dependendo do protocolo).

| Campo                  | Tipo      | Descrição                                                                         | Exemplo             |
| :--------------------- | :-------- | :-------------------------------------------------------------------------------- | :------------------ |
| `protocol`             | `string`  | O protocolo que o dispositivo utiliza (ex: `j16x_j16`, `jt808`, `vl01`, `nt40`).        | `"j16x_j16"`            |
| `output_protocol`      | `string`  | O protocolo de saída que o dispositivo utiliza (ex: `suntech4g`, `gt06`).        | `"suntech4g"`            |
| `imei`                 | `string`  | O IMEI do dispositivo.                                                            | `"358204012345678"` |
| `last_serial`          | `integer` | O último número de série do pacote recebido do dispositivo.                       | `"12345"`           |
| `last_active_timestamp`| `string`  | Timestamp UTC da última vez que o dispositivo enviou qualquer tipo de pacote (ISO 8601). | `"2023-10-27T10:35:00.123456+00:00"` |
| `last_event_type`      | `string`  | O tipo do último evento recebido (`location`, `heartbeat`, `alarm`, `information`). | `"location"`        |
| `total_packets_received`| `integer` | Contador total de pacotes recebidos do dispositivo desde o início.               | `"1501"`            |
| `last_packet_data`   | `JSON string` | Dados da última localização decodificada do protocolo, usados internamente para alertas (menos campos). | `{"latitude": -23.55, ...}` |
| `last_full_location`   | `JSON string` | Dados completos da última localização reportada, incluindo todos os detalhes.    | `{"timestamp": "2023-10-27T...", "latitude": -23.55, "speed_kmh": 60, ...}` |
| `odometer`             | `float`   | Odômetro calculado pelo servidor (em metros), baseado na distância Haversine. | `"12345678.90"`     |
| `acc_status`           | `integer` | Status da ignição (0: OFF, 1: ON).                                                | `"1"`               |
| `power_status`         | `integer` | Status da alimentação principal (0: Conectada, 1: Desconectada).                  | `"0"`               |
| `last_voltage`         | `float`   | Última voltagem da bateria do dispositivo reportada.                              | `"12.8"`            |
| `last_output_status`   | `integer` | Último estado da saída de controle (ex: bloqueio) (0: Desligado, 1: Ligado).     | `"1"`               |
| `last_command_sent`    | `JSON string` | Detalhes do último comando enviado do servidor para o dispositivo.             | `{"command": "RELAY 0", "timestamp": "...", "packet_hex": "..."}` |
| `last_command_response`| `JSON string` | Detalhes da última resposta de comando recebida do dispositivo. (Atualmente não implementado para todos os protocolos) | `{"response": "OK", "timestamp": "..."}` |

### Gerenciamento Avançado de Dados (Exemplo: Protocolo VL01)

O sistema permite a implementação de lógicas avançadas de gerenciamento de dados diretamente no gateway. O protocolo VL01, por exemplo, utiliza o [`mapper.py`](app/src/input/vl01/mapper.py) para enriquecer os dados brutos com informações calculadas pelo servidor.

#### Estratégias de Gerenciamento de Pacotes:

*   **Fila Persistente de Pacotes (Redis)**: Pacotes de localização, alarme e informação recebidos do protocolo VL01 são adicionados a uma fila persistente no Redis (`vl01_persistent_packet_queue`). Isso garante que os dados não sejam perdidos em caso de falha do servidor e permite o processamento ordenado.
*   **Processamento em Lotes**: A fila processa os pacotes em lotes de 30, garantindo que sejam tratados na ordem cronológica de seus timestamps (extraídos do próprio pacote quando disponíveis).

#### Informações Gerenciadas Exclusivamente pelo Servidor:

Alguns dados cruciais são calculados ou mantidos inteiramente no servidor, agregando inteligência aos dados brutos:

*   **Odômetro (`gps_odometer`)**: O valor do odômetro é calculado pelo servidor utilizando a fórmula de Haversine com base nas coordenadas de localização recebidas. Este valor é persistido no Redis e acumulado ao longo do tempo.
*   **Voltagem (`last_voltage`)**: A voltagem da bateria do dispositivo é extraída de pacotes de informação específicos e armazenada no Redis, permitindo um acompanhamento preciso do estado de energia do rastreador.

### Histórico de Pacotes (`history:<device_id>`)

Para cada dispositivo, uma lista é mantida no Redis contendo os pacotes brutos e seus respectivos pacotes Suntech4G traduzidos. Esta lista é limitada a `HISTORY_LIMIT` (definido em [`app/services/history_service.py`](app/services/history_service.py)) entradas.

| Campo            | Tipo      | Descrição                                         | Exemplo                       |
| :--------------- | :-------- | :------------------------------------------------ | :---------------------------- |
| `raw_packet`     | `string`  | O pacote original recebido do rastreador (hex).   | `"78780d01..."`               |
| `translated_packet` | `string`  | O pacote traduzido para o formato de saída.        | `">STT,IMEI,..."` ou `"7878..."` |

## Gerenciamento de Sessões TCP

O gateway gerencia ativamente as conexões TCP para garantir a comunicação bidirecional de forma eficiente e resiliente. A lógica é dividida em dois componentes principais, localizados em `app/src/session/`.

### Sessões de Entrada (Rastreador -> Gateway)

-   **Componente**: [`app/src/session/input_sessions_manager.py`](app/src/session/input_sessions_manager.py:10)
-   **Responsabilidade**: Manter um registro de todas as conexões TCP ativas vindas dos rastreadores.
-   **Funcionamento**: Utiliza um singleton (`InputSessionsManager`) que armazena os objetos de socket em um dicionário, usando o `device_id` como chave. Esse gerenciador é vital para o fluxo de **downlink**, pois permite que o sistema encontre rapidamente a conexão exata de um dispositivo para enviar comandos recebidos da plataforma principal.

### Sessões de Saída (Gateway -> Plataforma Principal)

-   **Componente**: [`app/src/session/output_sessions_manager.py`](app/src/session/output_sessions_manager.py:16)
-   **Responsabilidade**: Gerenciar as conexões de saída do gateway para a plataforma de rastreamento principal.
-   **Funcionamento**: Também implementado como um singleton (`OutputSessionsManager`), este módulo gerencia objetos de `MainServerSession`. Cada sessão representa uma conexão persistente para um `device_id` específico com o servidor final. Ele é responsável por:
    -   Estabelecer a conexão e autenticar o dispositivo (enviando pacotes de login).
    -   Manter a conexão ativa e reconectar em caso de falha.
    -   Encaminhar os pacotes de dados já traduzidos.
    -   Manter uma thread de escuta (`_reader_loop`) para receber comandos da plataforma (downlink) e roteá-los para o `builder` do protocolo de entrada correto.

Essa arquitetura de sessões desacoplada garante que o núcleo do sistema seja robusto a falhas de conexão e que o fluxo de comandos seja tratado de forma assíncrona e eficiente.

### Gerenciamento de Rastreadores Híbridos (GSM/Satélite)

O sistema possui uma lógica especializada para lidar com rastreadores "híbridos", que combinam comunicação GSM/GPRS com um rastreador satelital secundário. Em vez de tratar os dois como dispositivos separados, o gateway os unifica sob uma única identidade, enriquecendo os dados de um com o outro.

#### Fluxo de Dados Satelital:

1.  **Recepção e Mapeamento**: Um listener dedicado em [`app/src/input/satellital/handler.py`](app/src/input/satellital/handler.py:14) aguarda conexões de dispositivos satelitais. Ao receber um pacote, ele o encaminha para o [`mapper.py`](app/src/input/satellital/mapper.py:12).

2.  **Associação GSM**: O `mapper` extrai o Identificador Único do Equipamento (ESN) e consulta o Redis para encontrar o `device_id` (IMEI) do rastreador GSM correspondente. Essa associação é crucial, pois o dispositivo satelital atua como um "anexo" do GSM.

3.  **Fusão de Dados**: O sistema recupera a última localização enviada pelo rastreador GSM e a funde com os dados recebidos do satélite. Para diferenciar os pacotes, ele **sobrescreve** os seguintes campos:
    *   `voltage`: Alterado para `2.22` como um indicador de que a posição veio do módulo satelital.
    *   `satellites`: Alterado para `2` para sinalizar a origem satelital.

4.  **Envio Unificado**: O pacote híbrido resultante é enviado para a plataforma principal através da conexão e sessão já estabelecida pelo rastreador GSM ([`output_sessions_manager.py`](app/src/session/output_sessions_manager.py:269)), garantindo que a plataforma veja apenas um dispositivo, mas com dados enriquecidos de ambas as fontes.

## Rastreabilidade de Logs Aprimorada

O sistema utiliza um mecanismo de log contextual para garantir que cada operação possa ser rastreada até um dispositivo específico. Isso é alcançado através da injeção de um `log_label` (geralmente o IMEI do dispositivo) no contexto do logger.

### Como Funciona:

A função `logger.contextualize(log_label=dev_id)` é usada no início de cada thread de conexão de um rastreador (ex: em [`app/src/input/nt40/handler.py`](app/src/input/nt40/handler.py:22)). Uma vez que o contexto é definido, qualquer chamada subsequente ao logger (`logger.info`, `logger.error`, etc.), não importa de qual módulo ou função, incluirá automaticamente o `log_label` no registro de log.

**Exemplo de linha de log:**
```
INFO     | __main__: ✅ Protocol listener iniciado com sucesso na porta 7028 extra={'log_label': 'SERVIDOR'}
INFO     | app.src.input.nt40.handler: Nova conexão NT40 recebida endereco=('127.0.0.1', 49774) extra={'log_label': '358204012345678'}
```

Isso torna a análise de logs e a depuração de problemas de um dispositivo específico extremamente eficiente.

## Streaming de Logs em Tempo Real (WebSocket)

Para complementar a rastreabilidade dos logs, o sistema inclui um servidor WebSocket que transmite logs em tempo real para clientes conectados. Isso é ideal para depuração ao vivo e monitoramento do comportamento de um rastreador.

### Como Usar:

1.  **Conecte-se ao Servidor WebSocket**: O servidor é iniciado por padrão em `ws://<seu-host>:8575`.
2.  **Envie a Mensagem de Inscrição**: Após a conexão, envie uma mensagem no formato `"<tracker_id>|<numero_de_linhas>"`.
   *   `<tracker_id>`: O ID do dispositivo que você deseja monitorar.
   *   `<numero_de_linhas>`: O número de linhas de log históricas a serem exibidas no início do streaming (ex: `100`).

O servidor ([`app/websocket/ws.py`](app/websocket/ws.py:1)) então começará a transmitir todas as novas linhas de log que correspondem ao `tracker_id` fornecido.

## Protocolos Suportados

### Entrada

*   **GT06**: Um dos protocolos mais comuns em dispositivos de rastreamento genéricos.
*   **JT/T 808**: Um protocolo padrão robusto, amplamente utilizado em veículos comerciais.
*   **VL01**: Protocolo específico com gerenciamento avançado de dados no servidor.

### Saída

*   **Suntech4G**
*   **GT06**


## Endpoints da API

O servidor gateway expõe uma API RESTful para consulta de dados em tempo real e gerenciamento de sessões, facilitando a integração com outras plataformas e painéis de monitoramento. A lógica de gerenciamento de sessões de socket foi centralizada no diretório [`app/src/session/`](app/src/session/).

### `GET /trackers`
Retorna um dicionário com todos os dados dos rastreadores salvos no Redis, incluindo o status de conexão (`is_connected`).
Exemplo de Resposta:
```json
{
  "IMEI_DO_RASTREADOR_1": {
    "protocol": "j16x_j16",
    "last_active_timestamp": "2023-10-27T10:30:00.000000+00:00",
    "is_connected": true,
    "last_packet_data": "{\"latitude\": -23.55052, ...}",
    "odometer": "12345.67",
    "acc_status": "1",
    "power_status": "0",
    "last_voltage": "12.5",
    "imei": "IMEI_DO_RASTREADOR_1",
    "last_full_location": "{\"latitude\": -23.55052, ...}",
    "last_event_type": "location",
    "total_packets_received": "1500"
  },
  "IMEI_DO_RASTREADOR_2": {
    "protocol": "nt40",
    "is_connected": false,
    "last_active_timestamp": "2023-10-27T09:45:00.000000+00:00",
    "...": "..."
  }
}
```

### `GET /trackers/summary`
Fornece estatísticas de alto nível sobre os rastreadores no sistema.
Exemplo de Resposta:
```json
{
  "total_registered_trackers": 50,
  "total_active_translator_sessions": 25,
  "total_active_main_server_sessions": 20,
  "protocol_distribution": {
    "j16x_j16": 30,
    "jt808": 15,
    "vl01": 5
  },
  "total_packets_in_history": 120000,
  "most_recent_active_trackers": [
    {"device_id": "IMEI_RECENTE_1", "last_active_timestamp": "2023-10-27T10:35:00.000000+00:00"},
    {"device_id": "IMEI_RECENTE_2", "last_active_timestamp": "2023-10-27T10:34:00.000000+00:00"}
  ]
}
```

### `GET /trackers/<dev_id>/details`
Retorna detalhes abrangentes para um rastreador específico, incluindo dados do Redis e status de conexão.
Exemplo de Resposta:
```json
{
  "device_id": "IMEI_DO_RASTREADOR",
  "imei": "IMEI_DO_RASTREADOR",
  "protocol": "j16x_j16",
  "is_connected_translator": true,
  "is_connected_main_server": true,
  "last_active_timestamp": "2023-10-27T10:35:00.000000+00:00",
  "last_event_type": "location",
  "total_packets_received": 1501,
  "last_packet_data": { /* ... */ },
  "last_full_location": {
    "timestamp": "2023-10-27T10:35:00+00:00",
    "satellites": 8,
    "latitude": -23.55052,
    "longitude": -46.63330,
    "speed_kmh": 60,
    "direction": 90,
    "gps_fixed": 1,
    "acc_status": 1,
    "is_realtime": true,
    "gps_odometer": 12345.67,
    "voltage": 12.8
  },
  "odometer": 12345.67,
  "acc_status": 1,
  "power_status": 0,
  "last_voltage": 12.8,
  "last_command_sent": {
    "command": "RELAY 0",
    "timestamp": "2023-10-27T10:30:00.000000+00:00",
    "packet_hex": "..."
  },
  "last_command_response": {},
  "device_status": "Moving (Ignition On)"
}
```

### `POST /trackers/<dev_id>/command`
Envia um comando nativo para um rastreador específico através de sua conexão ativa.
**Corpo da Requisição:**
```json
{
  "command": "RELAY 0"
}
```
Exemplo de Resposta:
```json
{
  "status": "Command sent successfully",
  "device_id": "IMEI_DO_RASTREADOR",
  "command": "RELAY 0",
  "packet_hex": "..."
}
```

### `GET /trackers/<dev_id>/history`
Recupera o histórico de pacotes (brutos e traduzidos) para um rastreador específico.
Exemplo de Resposta:
```json
[
  {
    "raw_packet": "7878...",
    "translated_packet": ">STT..."
  },
  {
    "raw_packet": "7878...",
    "translated_packet": ">ALT..."
  }
]
```

### `GET /sessions/trackers`
Retorna uma lista dos IDs de dispositivos com sessões de socket ativas com o gateway tradutor.
Exemplo de Resposta:
```json
["IMEI_RASTREADOR_1", "IMEI_RASTREADOR_2"]
```

### `GET /sessions/main-server`
Retorna uma lista dos IDs de dispositivos com sessões ativas com o servidor principal.
Exemplo de Resposta:
```json
["IMEI_RASTREADOR_1", "IMEI_RASTREADOR_3"]
```

## Como Começar

Siga os passos abaixo para configurar e executar o servidor em seu ambiente de desenvolvimento.

### Pré-requisitos

*   Python 3.9+
*   Redis

### Instalação e Configuração

1.  **Clone o repositório:**
    ```bash
    git clone <url-do-seu-repositorio>
    cd <nome-do-repositorio>
    ```

2.  **Crie e ative um ambiente virtual:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # No Windows: `venv\Scripts\activate`
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure seu ambiente:**
    Crie um arquivo `.env` na raiz do projeto e preencha as variáveis de ambiente. Você pode usar o arquivo `.env.example` como modelo.
    ```
    LOG_LEVEL=INFO
    SUNTECH_MAIN_SERVER_HOST=127.0.0.1
    SUNTECH_MAIN_SERVER_PORT=12345
    GT06_MAIN_SERVER_HOST=127.0.0.1
    GT06_MAIN_SERVER_PORT=54321
    REDIS_DB_MAIN=2
    REDIS_PASSWORD=...
    REDIS_HOST=127.0.0.1
    REDIS_PORT=6379
    ```

### Executando o Servidor

Para iniciar o servidor, execute o arquivo [`main.py`](main.py):

```bash
python main.py
```
O servidor iniciará os listeners para todos os protocolos definidos em [`app/config/settings.py`](app/config/settings.py).

## Como Adicionar um Novo Protocolo

### Protocolo de Entrada

1.  **Crie o Diretório do Protocolo:**
    Dentro de `app/src/input/`, crie um novo diretório com o nome do seu protocolo (ex: `novo_protocolo`).

2.  **Implemente os Módulos Essenciais:**
    Crie os seguintes arquivos dentro do novo diretório, seguindo a estrutura dos módulos `j16x_j16` ou `jt808`:
    *   `handler.py`: Gerencia o ciclo de vida da conexão TCP.
    *   `processor.py`: Valida a integridade e disseca a estrutura dos pacotes.
    *   `mapper.py`: **O coração da tradução**. Converte os dados do protocolo para o dicionário Python padronizado.
    *   `builder.py`: Constrói pacotes no idioma nativo do protocolo para enviar respostas e comandos.

3.  **Registre o Protocolo:**
    Abra o arquivo [`app/config/settings.py`](app/config/settings.py) e adicione a configuração do seu novo protocolo no dicionário `INPUT_PROTOCOL_HANDLERS`:
    ```python
    INPUT_PROTOCOL_HANDLERS = {
        # ... protocolos existentes
        "novo_protocolo": {
            "port": 65434,  # Escolha uma porta livre
            "handler_path": "app.src.input.novo_protocolo.handler.handle_connection"
        }
    }
    ```

4.  **Habilite a Tradução Reversa de Comandos:**
    Em [`app/config/settings.py`](app/config/settings.py), importe a função `process_command` do seu novo `builder` e adicione-a ao dicionário `OUTPUT_PROTOCOL_COMMAND_PROCESSORS`.

### Protocolo de Saída

1.  **Crie o Diretório do Protocolo:**
    Dentro de `app/src/output/`, crie um novo diretório com o nome do seu protocolo (ex: `novo_protocolo`).

2.  **Implemente os Módulos Essenciais:**
    Crie os arquivos `builder.py` e `mapper.py` dentro do novo diretório, seguindo a estrutura dos módulos `suntech4g` ou `gt06`.
    *   `builder.py`: Deve conter as funções para construir os diferentes tipos de pacotes de saída (login, localização, heartbeat, etc.).
    *   `mapper.py`: Deve conter a função `map_to_universal_command` para traduzir comandos recebidos da plataforma principal para o formato universal.

3.  **Registre o Protocolo:**
    Abra o arquivo [`app/config/output_protocol_settings.py`](app/config/output_protocol_settings.py) e adicione a configuração do seu novo protocolo nos dicionários `OUTPUT_PROTOCOL_PACKET_BUILDERS`, `OUTPUT_PROTOCOL_COMMAND_MAPPERS`, e `OUTPUT_PROTOCOL_HOST_ADRESSES`.

## Estrutura do Projeto

A estrutura de diretórios foi organizada para separar claramente as responsabilidades, facilitando a manutenção e a adição de novas funcionalidades.

```
/
├── app/
│   ├── api/              # Módulo da API RESTful (endpoints para consulta)
│   ├── config/           # Arquivos de configuração (portas, protocolos, etc.)
│   ├── core/             # Componentes centrais (logger)
│   ├── services/         # Serviços de background (Redis, histórico)
│   └── src/              # Lógica principal da aplicação
│       ├── input/        # Módulos de protocolos de entrada (rastreadores)
│       │   ├── j16x_j16/
│       │   ├── nt40/
│       │   ├── satellital/
│       │   └── vl01/
│       ├── output/       # Módulos de protocolos de saída (plataforma)
│       │   ├── gt06/
│       │   └── suntech4g/
│       └── session/      # Gerenciamento de sessões TCP
├── main.py               # Ponto de entrada da aplicação
└── README.md             # Documentação do projeto
```

### Principais Componentes:

-   **`main.py`**: Orquestrador principal. Carrega as configurações, inicializa os listeners de protocolo em threads separadas e inicia a API.
-   **`app/config/settings.py`**: Define quais protocolos de entrada são carregados e em quais portas.
-   **`app/config/output_protocol_settings.py`**: Mapeia os protocolos de saída para seus respectivos `builders` e `mappers` de comando.
-   **`app/src/input/{protocolo}/`**: Cada diretório aqui representa um "dialeto" de rastreador.
   -   `handler.py`: Ponto de entrada da conexão TCP.
   -   `processor.py`: Valida e extrai dados do pacote bruto.
   -   `mapper.py`: Converte os dados para o formato padronizado do sistema.
   -   `builder.py`: Constrói comandos no formato nativo do rastreador (downlink).
-   **`app/src/output/{protocolo}/`**: Cada diretório representa um formato de saída para a plataforma.
   -   `builder.py`: Constrói pacotes (login, localização, etc.) no formato de saída.
   -   `mapper.py`: Converte comandos da plataforma para o formato universal.
-   **`app/src/session/`**: Contém os singletons que gerenciam as sessões de socket ativas, tanto de entrada quanto de saída, essenciais para a comunicação bidirecional.

## Tecnologias Utilizadas

*   **Python**: Linguagem principal do projeto.
*   **Redis**: Utilizado como uma memória de curto prazo para gerenciamento de estado das sessões e dos dispositivos.
*   **Pydantic**: Para gerenciamento de configurações e validação de dados.

