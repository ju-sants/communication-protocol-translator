# Servidor Gateway Poliglota para Rastreamento Veicular

Este não é apenas um servidor de rastreamento. É um **gateway de tradução universal**, projetado para resolver um dos maiores desafios no setor de telemétria: a **fragmentação de protocolos**. Com uma arquitetura modular e de alto desempenho, este projeto atua como a ponte definitiva entre centenas de modelos de rastreadores e a sua plataforma central.

## O Poder do Gateway Poliglota

A força deste projeto reside em sua arquitetura inteligente e desacoplada, que oferece funcionalidades muito além de uma simples tradução de dados.

*   **Arquitetura "Plug-and-Play"**: Adicionar suporte a um novo protocolo é tão simples quanto criar um novo diretório. A estrutura modular isola completamente a lógica de cada protocolo, permitindo que o sistema cresça sem complexidade adicional. O orquestrador em [`main.py`](main.py) carrega dinamicamente cada protocolo configurado em [`app/config/settings.py`](app/config/settings.py), iniciando listeners dedicados em threads separadas.

*   **Tradução para um Dicionário Universal**: A genialidade do sistema está na sua camada de `mapper` (ex: [`app/src/protocols/gt06/mapper.py`](app/src/protocols/gt06/mapper.py)). Cada `mapper` converte o dialeto específico de seu protocolo para um **dicionário Python padronizado**. Isso significa que a lógica de saída (o módulo Suntech) não precisa saber nada sobre os protocolos de entrada, garantindo um desacoplamento total.

*   **Geração de Eventos com Estado (Inteligência Agregada)**: O gateway não é um tradutor "burro". Utilizando o Redis ([`app/services/redis_service.py`](app/services/redis_service.py)), ele armazena o estado de cada dispositivo (como ignição ligada/desligada). Ao receber um novo pacote, ele compara o estado atual com o anterior e pode **gerar novos eventos de alerta** (ex: "Alerta de Ignição Ligada") que não existiam no protocolo original, agregando valor e inteligência aos dados brutos.

*   **Roteamento Reverso de Comandos**: O fluxo de comandos (downlink) é igualmente inteligente. Quando a plataforma principal envia um comando no formato Suntech, o [`app/src/connection/main_server_connection.py`](app/src/connection/main_server_connection.py) usa o Redis para identificar o protocolo de origem do dispositivo de destino. Em seguida, ele invoca o `builder` específico daquele protocolo (ex: [`app/src/protocols/gt06/builder.py`](app/src/protocols/gt06/builder.py)) para construir e enviar o comando no "idioma" nativo do rastreador.

## Arquitetura do Sistema

A arquitetura foi desenhada para máxima clareza, escalabilidade e manutenibilidade.

### Fluxo de Dados (Uplink: Dispositivo -> Plataforma)

Este diagrama mostra como os dados de um rastreador são recebidos, traduzidos e encaminhados para a plataforma final.

```mermaid
graph TD
    A[Dispositivo Rastreador] -- Pacote TCP --> B(Listener de Protocolo);
    B -- Bytes Brutos --> C{Handler};
    C -- Pacote Bruto --> D(Processor);
    D -- Dados Dissecados --> E(Mapper);
    E -- Dicionário Padrão --> F(Suntech Utils);
    F -- String Formato Suntech --> G(Main Server Connection);
    G -- Pacote TCP --> H[Plataforma Principal];

    subgraph "Módulo de Protocolo (Ex: GT06, JT808)"
        C
        D
        E
    end

    subgraph "Serviços Centrais"
        F
        G
    end
```

### Fluxo de Comandos (Downlink: Plataforma -> Dispositivo)

Este diagrama ilustra como os comandos são enviados da plataforma de volta para o dispositivo correto, na linguagem correta.

```mermaid
graph TD
    A[Plataforma Principal] -- Comando Suntech --> B(Main Server Connection);
    B -- Consulta Protocolo (DevID) --> C{Redis};
    C -- Retorna Protocolo (ex: 'gt06') --> B;
    B -- Comando + Protocolo --> D(Roteador de Comandos);
    D -- Comando para Builder Específico --> E{Builder do Protocolo};
    E -- Pacote Binário Nativo --> F(Socket do Dispositivo);
    F -- Pacote TCP --> G[Dispositivo Rastreador];

    subgraph "Serviços Centrais"
        B
        C
        D
    end

    subgraph "Módulo de Protocolo (Ex: GT06, JT808)"
        E
    end
```

## Dados Persistidos no Redis

O Redis é utilizado como um armazenamento de estado de curto prazo e cache para otimizar as operações do gateway. As chaves são categorizadas principalmente por `device_id` (IMEI) para dados do rastreador e chaves `history:<device_id>` para o histórico de pacotes.

### Hash de Dispositivo (`<device_id>`)

Para cada rastreador conectado ou que já se conectou, um hash é mantido no Redis sob a chave sendo o `device_id` (geralmente o IMEI em formato hexadecimal ou string, dependendo do protocolo).

| Campo                  | Tipo      | Descrição                                                                         | Exemplo             |
| :--------------------- | :-------- | :-------------------------------------------------------------------------------- | :------------------ |
| `protocol`             | `string`  | O protocolo que o dispositivo utiliza (ex: `gt06`, `jt808`, `vl01`, `nt40`).        | `"gt06"`            |
| `imei`                 | `string`  | O IMEI do dispositivo.                                                            | `"358204012345678"` |
| `last_serial`          | `integer` | O último número de série do pacote recebido do dispositivo.                       | `"12345"`           |
| `last_active_timestamp`| `string`  | Timestamp UTC da última vez que o dispositivo enviou qualquer tipo de pacote (ISO 8601). | `"2023-10-27T10:35:00.123456+00:00"` |
| `last_event_type`      | `string`  | O tipo do último evento recebido (`location`, `heartbeat`, `alarm`, `information`). | `"location"`        |
| `total_packets_received`| `integer` | Contador total de pacotes recebidos do dispositivo desde o início.               | `"1501"`            |
| `last_location_data`   | `JSON string` | Dados da última localização decodificada do protocolo, usados internamente para alertas (menos campos). | `{"latitude": -23.55, ...}` |
| `last_full_location`   | `JSON string` | Dados completos da última localização reportada, incluindo todos os detalhes.    | `{"timestamp": "2023-10-27T...", "latitude": -23.55, "speed_kmh": 60, ...}` |
| `odometer`             | `float`   | Odômetro calculado pelo servidor (em metros), baseado na distância Haversine. | `"12345678.90"`     |
| `acc_status`           | `integer` | Status da ignição (0: OFF, 1: ON).                                                | `"1"`               |
| `power_status`         | `integer` | Status da alimentação principal (0: Conectada, 1: Desconectada).                  | `"0"`               |
| `last_voltage`         | `float`   | Última voltagem da bateria do dispositivo reportada.                              | `"12.8"`            |
| `last_output_status`   | `integer` | Último estado da saída de controle (ex: bloqueio) (0: Desligado, 1: Ligado).     | `"1"`               |
| `last_command_sent`    | `JSON string` | Detalhes do último comando enviado do servidor para o dispositivo.             | `{"command": "RELAY 0", "timestamp": "...", "packet_hex": "..."}` |
| `last_command_response`| `JSON string` | Detalhes da última resposta de comando recebida do dispositivo. (Atualmente não implementado para todos os protocolos) | `{"response": "OK", "timestamp": "..."}` |

### Gerenciamento de Dados Específico do Protocolo VL01

O módulo [`mapper.py`](app/src/protocols/vl01/mapper.py:1) do protocolo VL01 implementa estratégias avançadas de gerenciamento de pacotes e enriquecimento de dados diretamente no servidor gateway.

#### Estratégias de Gerenciamento de Pacotes:

*   **Fila Persistente de Pacotes (Redis)**: Pacotes de localização, alarme e informação recebidos do protocolo VL01 são adicionados a uma fila persistente no Redis (`vl01_persistent_packet_queue`). Isso garante que os dados não sejam perdidos em caso de falha do servidor e permite o processamento ordenado.
*   **Processamento em Lotes**: A fila processa os pacotes em lotes de 30, garantindo que sejam tratados na ordem cronológica de seus timestamps (extraídos do próprio pacote quando disponíveis).

#### Informações Gerenciadas Exclusivamente pelo Servidor:

Alguns dados cruciais são calculados ou mantidos inteiramente no servidor para o protocolo VL01, agregando inteligência aos dados brutos:

*   **Odômetro (`gps_odometer`)**: O valor do odômetro é calculado pelo servidor utilizando a fórmula de Haversine com base nas coordenadas de localização recebidas. Este valor é persistido no Redis e acumulado ao longo do tempo.
*   **Voltagem (`last_voltage`)**: A voltagem da bateria do dispositivo é extraída de pacotes de informação específicos e armazenada no Redis, permitindo um acompanhamento preciso do estado de energia do rastreador.

### Histórico de Pacotes (`history:<device_id>`)

Para cada dispositivo, uma lista é mantida no Redis contendo os pacotes brutos e seus respectivos pacotes Suntech traduzidos. Esta lista é limitada a `HISTORY_LIMIT` (definido em [`app/services/history_service.py`](app/services/history_service.py)) entradas.

| Campo            | Tipo      | Descrição                                         | Exemplo                       |
| :--------------- | :-------- | :------------------------------------------------ | :---------------------------- |
| `raw_packet`     | `string`  | O pacote original recebido do rastreador (hex).   | `"78780d01..."`               |
| `suntech_packet` | `string`  | O pacote traduzido para o formato Suntech.        | `">STT,IMEI,..."`             |

## Protocolos Suportados

*   **GT06**: Um dos protocolos mais comuns em dispositivos de rastreamento genéricos.
*   **JT/T 808**: Um protocolo padrão robusto, amplamente utilizado em veículos comerciais.
*   **VL01**: Protocolo específico com gerenciamento avançado de dados no servidor.


## Endpoints da API

O servidor gateway expõe uma API RESTful para consulta de dados dos rastreadores e gerenciamento de sessões.

### `GET /trackers`
Retorna um dicionário com todos os dados dos rastreadores salvos no Redis, incluindo o status de conexão (`is_connected`).
Exemplo de Resposta:
```json
{
  "IMEI_DO_RASTREADOR_1": {
    "protocol": "gt06",
    "last_active_timestamp": "2023-10-27T10:30:00.000000+00:00",
    "is_connected": true,
    "last_location_data": "{\"latitude\": -23.55052, ...}",
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
    "protocol": "jt808",
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
    "gt06": 30,
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
  "protocol": "gt06",
  "is_connected_translator": true,
  "is_connected_main_server": true,
  "last_active_timestamp": "2023-10-27T10:35:00.000000+00:00",
  "last_event_type": "location",
  "total_packets_received": 1501,
  "last_location_data": { /* ... */ },
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
Recupera o histórico de pacotes (brutos e traduzidos para Suntech) para um rastreador específico.
Exemplo de Resposta:
```json
[
  {
    "raw_packet": "7878...",
    "suntech_packet": ">STT..."
  },
  {
    "raw_packet": "7878...",
    "suntech_packet": ">ALT..."
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
Retorna uma lista dos IDs de dispositivos com sessões ativas com o servidor principal Suntech.
Exemplo de Resposta:
```json
["IMEI_RASTREADOR_1", "IMEI_RASTREADOR_3"]
```

## Como Começar

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
    MAIN_SERVER_HOST=127.0.0.1
    MAIN_SERVER_PORT=12345
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

A arquitetura foi pensada para que a adição de novos protocolos seja um processo simples e direto:

1.  **Crie o Diretório do Protocolo:**
    Dentro de `app/src/protocols/`, crie um novo diretório com o nome do seu protocolo (ex: `novo_protocolo`).

2.  **Implemente os Módulos Essenciais:**
    Crie os seguintes arquivos dentro do novo diretório, seguindo a estrutura dos módulos `gt06` ou `jt808`:
    *   `handler.py`: Gerencia o ciclo de vida da conexão TCP.
    *   `processor.py`: Valida a integridade e disseca a estrutura dos pacotes.
    *   `mapper.py`: **O coração da tradução**. Converte os dados do protocolo para o dicionário Python padronizado.
    *   `builder.py`: Constrói pacotes no idioma nativo do protocolo para enviar respostas e comandos.

3.  **Registre o Protocolo:**
    Abra o arquivo [`app/config/settings.py`](app/config/settings.py) e adicione a configuração do seu novo protocolo no dicionário `PROTOCOLS`:
    ```python
    PROTOCOLS = {
        # ... protocolos existentes
        "novo_protocolo": {
            "port": 65434,  # Escolha uma porta livre
            "handler_path": "app.src.protocols.novo_protocolo.handler.handle_connection"
        }
    }
    ```

4.  **Habilite a Tradução Reversa de Comandos:**
    Em [`app/src/connection/main_server_connection.py`](app/src/connection/main_server_connection.py), importe a função `process_suntech_command` do seu novo `builder` e adicione-a ao dicionário `COMMAND_PROCESSORS`.

## Tecnologias Utilizadas

*   **Python**: Linguagem principal do projeto.
*   **Redis**: Utilizado como uma memória de curto prazo para gerenciamento de estado das sessões e dos dispositivos.
*   **Pydantic**: Para gerenciamento de configurações e validação de dados.
