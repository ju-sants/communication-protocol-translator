# 🚀 Servidor Tradutor de Protocolos de Rastreamento

![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)

Um gateway de telemetria de alta performance, assíncrono e poliglota, construído em Python. Este projeto atua como um servidor intermediário (proxy/tradutor) capaz de receber conexões de diversos modelos de rastreadores veiculares, cada um com seu próprio protocolo, e traduzir seus dados para um formato unificado antes de encaminhá-los para uma plataforma de destino.

O principal objetivo é resolver o problema de integração de hardware heterogêneo, permitindo que uma única plataforma de software receba dados de inúmeros dispositivos diferentes de forma transparente.

---

## ✨ Funcionalidades Principais

* **Arquitetura Poliglota "Plug-and-Play"**: Adicionar suporte a um novo protocolo de rastreador é tão simples quanto criar um novo módulo, sem a necessidade de alterar o núcleo do sistema.
* **Tradução Bidirecional**: Não apenas recebe e traduz dados dos rastreadores, mas também é capaz de receber comandos da plataforma final, traduzi-los para o protocolo específico do dispositivo e enviá-los de volta.
* **Gerenciador de Sessão Persistente**: Mantém conexões TCP persistentes e individuais tanto com os rastreadores quanto com a plataforma de destino, imitando o comportamento real dos dispositivos e garantindo a estabilidade da comunicação.
* **Geração de Eventos com Estado (Stateful)**: Utiliza Redis para armazenar o estado anterior dos dispositivos, permitindo a geração de eventos cruciais que não existem no protocolo original, como "Ignição Ligada/Desligada" e "Alimentação Principal Cortada/Restaurada".
* **Alta Performance e Escalabilidade**: Construído com uma arquitetura multithreading, onde cada conexão (seja de um rastreador ou para a plataforma) é gerenciada em sua própria thread, garantindo que o servidor seja responsivo e capaz de lidar com centenas de conexões simultâneas.
* **Configuração Centralizada**: Gerenciamento de todas as configurações sensíveis e de ambiente através de um arquivo `.env` e um módulo de settings robusto com Pydantic.

---

## 🏗️ Arquitetura do Sistema

O sistema foi projetado para ser modular e desacoplado. A comunicação flui de forma organizada através de componentes com responsabilidades únicas.

```mermaid
graph LR
    subgraph Dispositivo
        D1(Rastreador JT/T 808)
    end

    subgraph "Servidor Tradutor"
        L1[Listener na Porta 65432]
        
        subgraph "Módulo de Protocolo JT/T 808"
            direction LR
            H1[Handler] --> P1[Processor]
            P1 --> M1[Mapper]
        end

        CM[Connection Manager]
        PF(Plataforma Suntech)
    end

    D1 -- "Pacote Binário" --> L1
    L1 --> H1
    M1 -- "Dados Unificados (Dicionário Python)" --> CM
    CM -- "Pacote Suntech (ASCII)" --> PF

    style D1 fill:#d4edda,stroke:#155724
    style PF fill:#cce5ff,stroke:#004085
    style M1 fill:#fff3cd,stroke:#856404