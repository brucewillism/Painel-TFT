# Painel TFT — dashboard auxiliar para qualquer carro

Primeira versão de um painel auxiliar para **Raspberry Pi 4 ou 5** com tela de
**7" (800×480)**. Funciona com qualquer carro que fale OBD2 (ELM327 ou HAT
CAN). O Mitsubishi Lancer HL 2016 (Brasil, CVT) entra como **um dos perfis de
exemplo**, não como o único modelo suportado.

Esta versão **não substitui o painel original**. O cluster de fábrica fica no
lugar; esta tela entra como auxiliar (console, suporte 3D ou encaixe no painel).

## O que ele mostra

No arranque o software **descobre os PIDs que a ECU realmente suporta** e
exibe o que estiver disponível:

- RPM, velocidade, temperatura do motor e da admissão
- Carga do motor, posição do acelerador, MAF, MAP
- Sondas lambda (O2), trims de combustível (STFT/LTFT), avanço de ignição
- Tensão da bateria (comando ATRV do ELM327 ou PID 0x42 da ECU)
- Nível de combustível (se a ECU expuser o PID 0x2F — muitos Lancers não
  expõem pelo OBD genérico)
- Tempo com o motor ligado, pressão barométrica, temperatura ambiente
- Códigos de falha (DTC): leitura e apagamento com confirmação
- Valores derivados: consumo instantâneo e médio (estimado pelo MAF),
  distância da viagem e **relação efetiva da CVT** (RPM por km/h, relação
  das polias e relação total motor/roda). A estimativa de marcha de um
  câmbio manual 5 velocidades existe, mas vem **desligada** — o HL 2016
  brasileiro é CVT Jatco (`transmission: cvt` no `config.yaml`).
- GPS: posição ao vivo, rastro da viagem, velocidade GPS, rumo, altitude e
  satélites
- Temperatura do fluido da CVT: experimental, via Mode 22 na TCM (desligada
  por padrão; veja a seção abaixo)
- **Início**: tela inicial tipo central multimídia, com atalhos (Painel,
  Mapa, CarPlay, Música, Telefone, Câmeras, Rádio, Ajustes, Carro,
  Sensores, Viagem, Falhas, **PERF, Pista, G-Force, Log, Dash, Saúde, LED, Valet**)
- **Carro**: ilustração do tipo de carroceria (sedã, hatch, SUV,
  picape, cupê, perua — sem logotipos oficiais) ou, quando houver internet na
  primeira vez, uma **foto real do modelo** (Wikimedia Commons, licença
  livre, cache local). Faróis, setas, freio e rodas animam nos dois modos.
- **Câmeras**: até 4 USB/UVC + ré, grade ou tela cheia, 360° experimental
- **Mídia**: pasta local, rádio online, Bluetooth A2DP/AVRCP e equalizador
- **Telefone**: mãos-livres (HFP via oFono/BlueZ), agenda (PBAP) e registro
- **Rádio**: FM opcional (RTL-SDR) + rádio online
- **CarPlay / Android Auto**: dongle USB estilo Carlinkit (ligado ou
  wireless) com o driver open-source node-CarPlay / react-carplay
- **Desempenho**: cronômetro 0–100, 80–120, 402 m e 100–0, com auto
  start/stop, fusão GPS+OBD e histórico dos melhores tempos
- **Pista**: cronômetro de volta com portão de largada/chegada, setores,
  delta ao vivo vs. melhor volta, traçado e sessões gravadas
- **G-Force**: círculo de atrito com rastro e picos (IMU I2C ou estimativa
  pelo GPS/velocidade)
- **Telemetria**: gravação de RPM, velocidade, acelerador, temps, G e GPS,
  gráficos e exportação CSV
- **Dash cam**: gravação com overlay (ffmpeg), loop com limite de espaço e
  proteção de clipe em evento de G ou no botão
- **Shift light**: pontos de RPM configuráveis (modo Sport/manual do CVT),
  barra visual e beep/voz na saída de áudio
- **Saúde**: revisões por km/tempo (óleo, CVT, filtros, pneus), hodômetro
  (ajuste manual + distância GPS/OBD), histórico de DTC e bateria
  (queda na partida e tendência em repouso)
- **LEDs ambiente**: fita WS2812/WS2815 no GPIO, modos RPM / música /
  alertas / cor fixa, também pelo app do celular
- **TPMS**: sensores BLE externos, pressões e temperaturas na página Carro
- **Valet**: modo travado por PIN, log de velocidade máxima, rota e
  eventos bruscos, com relatório ao destravar

Alertas visuais para temperatura alta do motor, tensão baixa/alta, RPM alto
e (quando houver leitura) fluido da CVT quente.

## Hardware — lista de compras

Lista com links de compra e preços em reais, conferidos em 13 de novembro de 2026 (America/Sao_Paulo), para o Painel TFT v0.4.3: [docs/lista-de-compras.md](docs/lista-de-compras.md). O kit **Básico** é o mínimo para o HUD ligar no carro com OBD, GPS e mapa (Pi 4 4 GB); o kit **Final** troca para Pi 5 4 GB (WebGL + CarPlay) e soma CAN, optoacoplador, câmeras, áudio, IMU e LEDs. O ELM327 v2.1 Bluetooth que você já tem entra como item já possuído.


| Item | Observação |
| --- | --- |
| Raspberry Pi 4 (4 GB) ou Pi 5 | O Pi 4 esquenta menos no painel fechado e já dá conta. |
| Tela 7" 800×480, de preferência IPS e touch | Oficial Raspberry Pi 7" ou HDMI IPS de bom brilho (sol). |
| Conversor buck 12 V → 5 V **3 A ou mais** (USB-C no Pi 4/5) | Ligar na **ignição / ACC**, nunca direto na bateria sem corte. |
| Cartão microSD 32 GB de marca boa **ou SSD USB de 128 GB+** | SSD aguenta melhor o calor. Para **dash cam**, prefira 128–256 GB (o loop apaga clipes antigos). |
| Dissipador + ventoinha | Carro parado no sol esquenta muito. |
| Módulo GPS USB u-blox NEO-6M ou, de preferência, **NEO-7M / M8 a 10 Hz** | Aparece como `/dev/ttyACM0` ou `/dev/ttyUSB*`; o `gpsd` cuida. Para cronômetros de arrancada, 10 Hz faz diferença (veja `scripts/ublox-10hz.sh`). O NEO-6M em 9600 baud às vezes não sustenta 10 Hz com NMEA completo — prefira 115200 e um 7M/M8. |
| ELM327 Bluetooth (clone v2.1 serve para começar) | O que você já tem. Lento (~3–8 PIDs/s). PIN típico **1234**. |
| *(depois)* HAT CAN MCP2515 | Ligado nos pinos 6 (CAN-H) e 14 (CAN-L) do OBD2, 500 kbit/s 11-bit. |
| Dongle USB CarPlay / Android Auto (Carlinkit CPC200-CCPA, 4.0 ou 5.0) | Ligado ou wireless. IDs USB típicos `1314:1520/1521/1522` e `08e9:0001`. Sem dongle a tela CarPlay é um mock. |
| Câmeras USB/UVC (até 4) e/ou conversor AV→USB para câmera de ré analógica | Use um **hub USB alimentado**; 4 câmeras MJPEG saturam a porta do Pi. |
| DAC USB ou áudio HDMI/aux | O HDMI da tela 7" oficial às vezes não tem linha de som decente. |
| Microfone USB (ou headset) | Para CarPlay e chamadas HFP. |
| *(opcional)* dongle RTL-SDR (RTL2832U) | Rádio FM de verdade via `rtl_fm`. Sem ele, o sintonizador é só visual — o rádio online continua funcionando. |
| IMU I2C **MPU-6050**, **MPU-9250** ou **ICM-20948** | G-meter. I2C1 do Pi: VCC→3V3, GND, SDA→pino 3, SCL→pino 5, endereço 0x68. Calibre parado com `scripts/imu-calibrate.py`. Sem IMU, o G é estimado pelo GPS/velocidade. |
| Fita LED **WS2812 (5 V)** ou **WS2815 (12 V)** + **transmissor de nível 3V3→5V** (74AHCT125 ou equivalente) + **fonte 5 V dedicada** | Iluminação ambiente no GPIO 18 (PWM0). Não alimente a fita pelo pino 5 V do Pi. GND comum com o Pi. |
| Sensores **TPMS BLE** externos (os baratos de válvula, 4 unidades) | Anúncios BLE decodificados pelo painel (`bleak` no Pi). Vincule cada sensor a uma roda na configuração. |

Opcionais úteis: módulo de *ignition sense* / desligamento seguro (GPIO que
avisa o Pi antes de cortar a 12 V), cabo OBD2 “Y” se for usar o HAT CAN
junto da tomada de diagnóstico, um suporte impresso em 3D, e um hub USB
alimentado se for empilhar dongle CarPlay + câmeras + GPS + DAC + dongle BLE
(se o Bluetooth interno estiver ocupado com o ELM327).

## Ligação elétrica (resumo)

```
Bateria 12 V ── fusível ── chave de ignição (ACC/IGN)
                               │
                               ├── conversor buck 12 V → 5 V 3 A ── USB-C do Pi
                               │
                               └── (opcional) divisor/módulo ignition-sense ── GPIO

Tomada OBD2 do Lancer (embaixo do volante, lado esquerdo):
  pino 16 = 12 V permanente    pinos 4 e 5 = GND
  pino  6 = CAN-H              pino 14     = CAN-L

  • Fase 1: encaixe o ELM327 na tomada. O Pi fala com ele via Bluetooth
    (/dev/rfcomm0). Não precisa soldar nada.
  • Fase 2: tire o ELM e ligue o HAT MCP2515 em CAN-H/CAN-L (e GND).
    Configure no config.yaml  source: can
```

**Não ligue o Pi direto nos 12 V.** Use um buck de qualidade, com filtro se
possível (o alternador e o arranque geram ruído e picos).

### Desligamento seguro (importante)

Se você simplesmente corta a ignição, o Pi perde energia no meio da escrita
do cartão e o sistema pode corromper. Caminhos possíveis:

1. **Módulo de ignição** (tipo “ignition sense / UPS para Pi”): a 12 V
   permanente alimenta um capacitor/UPS pequeno; o ACC avisa um GPIO; o
   painel chama `systemctl poweroff` (o endpoint `/api/shutdown`, já
   preparado, exige `LANCER_ALLOW_SHUTDOWN=1`) e só então a energia cai.
2. Enquanto isso não existe, desligue pelo botão **Desligar o Pi** na página
   Ajustes e espere apagar, ou dê `sudo shutdown -h now` por SSH, e só
   então tire a chave.

## Software — arquitetura

Camadas separadas, para trocar o ELM327 pelo HAT CAN sem mexer na interface:

- `app/sources/` — fontes com a mesma interface (`connect`, `discover`,
  `read_pid`, `read_dtcs`, `clear_dtcs`):
  - `obd_source.py` — python-OBD em `/dev/rfcomm0` (ou outra serial)
  - `can_source.py` — python-can / SocketCAN, pedido Mode 01 no ID `0x7DF`,
    resposta `0x7E8`, 500 kbit/s 11-bit
  - `gps_source.py` — gpsd (USB u-blox)
  - `simulator.py` — veículo virtual + GPS, para desenvolver sem o carro
- `app/store.py` — depósito central dos sinais
- `app/scheduler.py` — varredura com prioridade (RPM/velocidade sempre;
  o resto em rodízio, cabendo no orçamento lento do ELM327)
- `app/derived.py` / `app/alerts.py` / `app/trips.py` / `app/cvt_uds.py` —
  consumo, relação da CVT (ou marcha manual), alertas, Mode 22 experimental,
  log SQLite e exportação GPX
- `app/cameras.py` — hubs UVC/MJPEG, placeholder no simulador, GPIO da ré,
  esboço de 360° (homografia)
- `app/media.py` / `app/phone.py` / `app/carplay.py` / `app/fm_radio.py` —
  mídia, HFP, dongle CarPlay, FM RTL-SDR
- UI web (FastAPI + WebSocket) servida em tela cheia no Chromium kiosk

### Por que UI web e não PyQt

A tela é 800×480 touch, o Chromium em modo kiosk já é o caminho natural no
Pi, o WebSocket atualiza a 12 Hz e os ponteiros interpolam no
`requestAnimationFrame` (ficam lisos mesmo com o ELM327 lento). O Leaflet
resolve o mapa offline/online, e o mesmo código roda no computador para
teste. PyQt também serviria, mas pesa mais para instalar e não ajuda no
kiosk nem no mapa.

## Instalação no Raspberry Pi

```bash
sudo apt-get update
git clone <este-repositório> ~/lancer-painel   # ou copie a pasta / o zip
cd ~/lancer-painel
chmod +x scripts/*.sh
./scripts/install.sh
```

O script cria um `.venv`, instala as dependências, habilita o serviço
`lancer-painel` e o autostart do kiosk.

### Parear o ELM327 Bluetooth

PIN típico dos clones: **1234** (às vezes `0000`).

```bash
sudo ./scripts/pair-elm327.sh
# ou, se você já souber o MAC:
sudo ./scripts/pair-elm327.sh AA:BB:CC:DD:EE:FF
```

Isso cria `/dev/rfcomm0` e tenta gravar o bind em `/etc/bluetooth/rfcomm.conf`
para sobreviver ao reboot. No `config.yaml`:

```yaml
source: obd
obd:
  port: /dev/rfcomm0
  baudrate: 38400
```

Teste rápido: `python3 -c "import obd; c=obd.OBD('/dev/rfcomm0'); print(c.status(), c.query(obd.commands.RPM))"`

### GPS (gpsd)

```bash
# o módulo USB em geral aparece como /dev/ttyACM0
sudo systemctl enable --now gpsd
cgps -s     # deve mostrar fix depois de alguns segundos, com visão do céu
```

No Raspberry Pi OS o `gpsd` costuma detectar o u-blox sozinho. Se não,
edite `/etc/default/gpsd` com `DEVICES="/dev/ttyACM0"`.

### Fase 2 — HAT MCP2515 (SocketCAN)

No `config.txt` do Pi (exemplo, ajuste os pinos do seu HAT):

```
dtparam=spi=on
dtoverlay=mcp2515-can0,oscillator=8000000,interrupt=25
```

No boot (ou num `systemd`):

```bash
sudo ip link set can0 up type can bitrate 500000
```

E no `config.yaml`: `source: can`. A interface do painel não muda.

## Rodar em modo simulador (sem o carro)

No próprio Pi ou em qualquer Linux com Python 3.11+:

```bash
cd lancer-painel
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
LANCER_SOURCE=simulator ./scripts/run-simulator.sh
# abra http://127.0.0.1:8080/
```

O simulador gera um Lancer 2.0 **CVT** em ciclo urbano: o RPM sobe e
segura (efeito elástico da Jatco) enquanto a velocidade sobe, depois
cai no cruzeiro. Há também um percurso de GPS pela Av. Paulista.
Para testar o modo manual: `transmission: manual` no `config.yaml`.

## Rodar no carro

1. Pareie o ELM327 e confirme `/dev/rfcomm0`.
2. Em `config.yaml` (ou nas variáveis do serviço): `source: obd`.
3. `sudo systemctl start lancer-painel` (e o kiosk no autostart).
4. Encaixe o ELM327, ligue a ignição, espere o pill **OBD** ficar verde.
5. Com o GPS no para-brisa (visão do céu), o pill **GPS** fica verde e o
   mapa passa a traçar o rastro.

A primeira conexão de um clone v2.1 às vezes trava: tire e recoloque o
adaptador, ou `sudo rfcomm release 0 && sudo rfcomm bind 0 MAC 1`.

## Mapa offline (tiles)

O painel tenta, nesta ordem:

1. Pasta local `app/static/tiles/{z}/{x}/{y}.png`
2. Arquivo MBTiles em `data/region.mbtiles`
3. Fallback online (Esri Dark Gray, precisa de internet no Pi — no carro
   isso só existe se houver um hotspot). Sem chave de API.

Para pré-baixar uma região pequena (ex.: sua cidade), respeitando a
[política de uso dos tiles da OSM](https://operations.osmfoundation.org/policies/tiles/):

```bash
# SUL OESTE NORTE LESTE  zoom-mín zoom-máx
./scripts/download-tiles.sh -23.58 -46.67 -23.55 -46.63 12 16
```

Para uma região grande, gere um `.mbtiles` com o
[Mobile Atlas Creator (MOBAC)](https://www.mobileatlascreator.org/) ou com
o [tilemaker](https://github.com/systemed/tilemaker) e copie para
`data/region.mbtiles`. O servidor inverte o eixo Y TMS automaticamente.

## Páginas da interface (toque / deslize)

A tela **Início** é o lançador da central, com os tiles **Painel**, **Mapa**,
**CarPlay**, **Música**, **Telefone**, **Câmeras**, **Rádio** e **Ajustes**
(e ainda Carro, Sensores, Viagem, Falhas). A barra inferior traz os
atalhos mais usados. Deslize para trocar de página.

- **Painel** — RPM, velocidade, relação da CVT (ou marcha, se manual),
  temp. do motor, tensão, barras e *shift light* no topo. Layout pensado
  para 800×480: os medidores laterais não encostam na barra de combustível.
- **Carro** — sedan estilizado (sem logotipo oficial da Mitsubishi), com
  faróis, setas, luz de freio, rodas na velocidade e leve inclinação na
  aceleração/freada. Vista de cima destaca motor, bateria e CVT em alerta.
- **Câmeras** — grade 2×2, câmera única ou vista 360°. Ao detectar a ré
  (GPIO ou hook `/api/cameras/reverse`) a tela salta automaticamente para
  a câmera traseira.
- **Mídia** — pasta `data/music`, rádio online, Bluetooth A2DP/AVRCP
  (BlueZ) e equalizador de 5 bandas.
- **Telefone** — discar, atender, agenda e registro. No simulador tudo é
  mock (há um botão “Simular chamada”).
- **Rádio** — sintonizador FM (RTL-SDR, se houver) + lista de rádio online.
- **CarPlay** — tela cheia com o mock da central, ou lança o driver do
  dongle (`scripts/carplay-launch.sh`). O botão **← Painel** volta ao
  lançador e encerra o processo do dongle.
- **Mapa / Sensores / Viagem / Falhas / Ajustes** — como antes; em Ajustes
  dá para escolher o tema **vermelho** (padrão) ou **âmbar**.

Modo noturno automático das 18h às 6h no fuso `America/Sao_Paulo` (ou no pôr do sol, se escolher essa opção — calculado no Pi a partir do GPS, sem API).

Há também o **app companheiro** no celular (`/app`): um PWA instalável que muda tema, brilho, modo noturno, desempenho, cor do carro e quais medidores aparecem no Painel. As mudanças chegam ao dashboard na hora pelo WebSocket. Um PIN evita que qualquer pessoa na rede bagunce os ajustes (o kiosk local, em 127.0.0.1, continua salvando sem PIN).

O mapa ganhou o modo **Postos**: estima se a gasolina que está no tanque dá para chegar, com consumo recente (cidade/estrada) e, quando houver chave e internet, o atraso de trânsito. A navegação tipo Waze permanece fora desta tela — as rotas usam o mapa que o painel já tem.

## CVT, consumo e marcha — limitações

O Lancer HL 2016 no Brasil sai de fábrica com **CVT Jatco** (família
JF011E / F1CJA; no modo Sport alguns anos simulam “degraus”). Por isso o
padrão é `transmission: cvt`. Nesse modo o painel **não** tenta adivinhar
uma marcha 1–5. Em vez disso mostra:

- relação das polias (estimada a partir de RPM, velocidade, circunferência
  do pneu 205/60R16 e diferencial típico 6,386)
- relação total (voltas do motor por volta da roda)
- RPM por km/h, com uma barra LOW → HIGH que se move com suavidade

Se o seu carro for o manual de 5 marchas, mude no `config.yaml` (ou em
Ajustes) para `transmission: manual`. Aí entra a estimativa antiga
(relações 3,538…0,687 + diferencial 4,235).

### Temperatura do fluido da CVT (experimental)

Essa grandeza **não** é um PID Mode 01 padrão. Ela mora na TCM, em geral
via UDS **Mode 22** (ReadDataByIdentifier) no ID CAN `0x7E1` (resposta
`0x7E9`). No `config.yaml`:

```yaml
cvt:
  fluid_temp_enabled: false   # ligue só depois de confirmar o DID
  tcm_request_id: 0x7E1
  tcm_response_id: 0x7E9
  did: 0x2101                 # ponto de partida — confirme no seu carro
  decode: a_minus_40          # A−40 °C; alternativas: u16_minus_40, raw_a
```

- Na fonte **CAN** (HAT MCP2515) o pedido vai direto para a TCM.
- No **ELM327** o software tenta `ATSH 7E1` e depois restaura `ATSH 7DF`.
  Clones v2.1 costumam ignorar ou travar o header — deixe desligado até
  ter o HAT, ou teste com cuidado.
- O DID `0x2101` é um ponto de partida comum em Jatco/Mitsubishi, **não**
  uma garantia. Confirme com um log CAN (ou um scanner que já mostre o
  ATF) antes de confiar no número.
- Quando houver leitura, o alerta de fluido quente (padrão 120 °C) aparece
  em Ajustes e no topo do painel. No modo simulador a temperatura é
  gerada junto com os outros sinais, para você ver o indicador.

### Consumo

- O consumo instantâneo/médio é **estimado** a partir do MAF e de um AFR
  (gasolina 14,7 / etanol 9,0 / flex interpolado, padrão E27 no Brasil).
  Não substitui o computador de bordo. Se a ECU expuser o PID 0x5E
  (vazão em L/h), ele tem prioridade.
- Nem todo PID da lista aparece em todo Lancer; o que a ECU não responder
  simplesmente não entra na tela.

## Visual — HUD wireframe (padrão) e Clássico vermelho

O tema padrão é o **HUD Reator**: fundo preto técnico, números digitais
grandes, carro 3D em wireframe (three.js, empacotado offline em
`app/static/vendor/three.min.js`, licença MIT) girando devagar sobre anéis
holográficos, e acento ciano **Reator arc** (`#00D8FF`) com brilho
branco-quente. A cor de destaque é configurável ao vivo (WebSocket) nos
Ajustes e no app do celular (`/app`), com presets:

- Reator arc `#00D8FF` (padrão)
- Vermelho `#E10600`
- Verde Matrix `#00FF6A`
- Âmbar `#FFB000`
- Roxo `#B14CFF`
- Branco `#F4FBFF`
- ou um seletor de cor livre (`accent: custom`)

O visual antigo (medidores circulares, acento vermelho) permanece como
tema **Clássico vermelho** (`ui.theme: classic`). Fontes Orbitron e
Rajdhani vêm em `app/static/fonts/` (uso offline, SIL OFL). Sem logotipos
oficiais.

No perfil do **Lancer HL 2016**, o herói do HUD não é o modelo 3D
genérico: é uma **ilustração holográfica em wireframe do próprio Lancer
2016**, gerada por IA a partir da foto do Wikimedia Commons
*File:2016 Mitsubishi Lancer (CF MY16) ES Sport sedan (2016-11-13) 01.jpg*
(autor **EurovisionNim**, CC BY-SA 4.0). Os PNGs ficam em
`data/vehicles/2016_Mitsubishi_Lancer/hud-wireframe.png` (cor + alfa) e
`hud-wireframe-luma.png` (máscara de luminância para recolorir). O fundo
preto vira transparente pela intensidade das linhas (não usamos rembg,
para não apagar o brilho). A cor segue o acento atual (Reator arc, Matrix,
Âmbar…) via máscara CSS + um núcleo branco nas linhas claras. A imagem
fica centrada nos anéis holográficos, com as rodas no plano dos anéis, um
flutuação lenta de 2–3 px, um pulso de brilho, uma linha de varredura
recortada na silhueta e os anéis girando. Tudo isso é CSS
(`transform`/`opacity`) para caber no Pi. O botão de pausa interrompe
essas animações. Os callouts (motor, CVT, bateria, roda dianteira) usam
coordenadas normalizadas gravadas no perfil (`hud_hero.anchors`).

Os demais perfis continuam com o **carro 3D** em wireframe. O tipo
**sedan** (padrão, quando não há `hud_hero`) usa o **Sedan car** da
Innerscene (CC0 1.0, escala real, ~4,55 m —
https://www.innerscene.com/tools/library/3d-parts/sedan-car-42109739)
em `app/static/models/innerscene/sedan.glb`. Os outros tipos vêm do
**Kenney Car Kit** (CC0 1.0, https://kenney.nl/assets/car-kit) em
`app/static/models/kenney-car/`: hatch → `hatchback-sports`, SUV → `suv`,
picape → `truck`, cupê → `sedan-sports`, perua → `van` (o kit não tem
perua; a van é o mais próximo). Eles são desenhados como wireframe técnico
(preenchimento escuro translúcido, arestas `EdgesGeometry`, grade suave,
brilho aditivo e faróis/lanternas emissivos), em ângulo 3/4 dianteiro, apoiados nos anéis holográficos, com uma oscilação
curta em torno desse ângulo (para as linhas de callout continuarem apontando para o capô, o câmbio, a bateria e a roda dianteira). Créditos e o texto das
licenças estão em `LICENSES`. O three.js (r152, MIT) fica em
`app/static/vendor/three.min.js`.

Há um botão no palco (e um ajuste) para **pausar a rotação** (e, no herói
2D, a flutuação, a varredura e o pulso). No Pi 4
(800×480) o alvo é 30+ fps; ligue o **modo desempenho**
(`ui.performance_mode: true`) se precisar: desliga o antialias e reduz o
*pixel ratio*.

```yaml
ui:
  theme: hud                 # hud | classic
  accent: arc
  accent_hex: "#00D8FF"
  hud_rotate: true
  unused_telltales: dim      # dim | hide
  performance_mode: false
```

## Marcha e luzes (não são OBD2 padrão)

**Marcha / posição do câmbio** e **faróis, setas, lanterna, freio de mão,
portas e cinto** não existem como PIDs Mode 01 universais. O Painel TFT
trata isso em fontes próprias. O *check engine* é a exceção: vem do **MIL
(Mode 01 PID 01)**.

### Marcha (`gear_source`)

No perfil (`profiles/*.yaml`) ou no `config.yaml`:

```yaml
gear_source: inferred   # inferred | can | gpio
```

- `inferred` (padrão): com o câmbio automático/CVT, **P** parado com o
  motor desligado ou o freio de mão puxado, **N** na lenta, **D** em
  movimento, **R** se houver sinal de ré. No perfil manual, em movimento
  permanece a estimativa 1–6 (relações do perfil).
- `can`: decodifica um quadro configurável (para o HAT MCP2515). Informe
  `gear_can.id`, `byte`, `mask`, `shift` e `map` (ex.: `0: P, 3: D`).
- `gpio`: lê pinos BCM (mapa `gear_gpio.pins` ou só um `reverse_pin`).

### Luzes (`lights`)

Backends: `sim`, `gpio`, `can`, ou `auto` (simulador quando a fonte do
veículo é o simulador; senão GPIO se houver pinos, senão CAN). Telltales
sem fonte configurada ficam esmaecidos ou ocultos (`ui.unused_telltales`).
No simulador todos são acionados (farol baixo e lanterna ligados, setas
piscando na lenta, freio de mão e cinto na ignição).

### Fiação do optacoplador (PC817) — 12 V → GPIO com segurança

**Nunca ligue 12 V direto num pino do Raspberry Pi.** Use um módulo
optacoplador (PC817 ou equivalente):

1. Lado 12 V (lâmpada / sinal do farol, seta, lanterna, freio de mão):
   o positivo do circuito (após o interruptor, junto do fio que acende a
   lâmpada) entra no LED do PC817 através de um resistor **1 kΩ a 2,2 kΩ /
   0,5 W**. O outro terminal do LED vai ao GND do carro (chassis).
2. Lado do Pi (3,3 V): o emissor do transistor do PC817 vai ao **GND do
   Pi** (GND comum com o carro). O coletor vai ao pino BCM configurado.
   No `config.yaml`, `active_low: true`: o GPIO usa *pull-up*; quando a
   lâmpada acende, o PC817 conduz e o pino vai a 0 V.
3. Repita um canal por sinal. Exemplo de pinos (pode trocar):

   | Sinal           | Pino BCM (exemplo) |
   |-----------------|--------------------|
   | Farol baixo     | 5                  |
   | Farol alto      | 6                  |
   | Lanterna        | 13                 |
   | Seta esquerda   | 19                 |
   | Seta direita    | 26                 |
   | Freio de mão    | 16                 |
   | Porta aberta    | 20                 |
   | Cinto           | 21                 |

4. No carro, confirme o fio com um multímetro (12 V só com a função
   ligada) antes de soldar. Deixe `pin: null` nos sinais que você ainda
   não ligou — o telltale correspondente fica esmaecido ou oculto.

A leitura no Pi tenta `gpiozero` e, se não houver, `gpiod` / sysfs. No
desenvolvimento (sem GPIO) a fonte é simplesmente ignorada ou simulada.

## Estrutura do projeto

```
lancer-painel/
  config.yaml            # configuração padrão
  requirements.txt
  profiles/              # YAML por veículo (Lancer, Onix, Compass, Hilux, …)
  app/
    main.py              # FastAPI, rotas, WebSocket /ws
    profiles.py          # carga, merge e casamento de perfis
    vin.py               # WMI offline + vPIC opcional
    car_photo.py         # Commons, rembg/u2netp, orientação, zonas
    vehicle_api.py       # /api/vehicle, arte, assistente, galeria
    store.py scheduler.py signals.py
    derived.py alerts.py trips.py tiles.py cvt_uds.py
    cameras.py media.py phone.py carplay.py fm_radio.py gpio_reverse.py
    range.py companion.py sun.py
    sources/             # obd, can, gps, simulador
    static/  templates/  # UI (tema vermelho, home, carro, câmeras, mídia)
    static/img/bodies/   # 6 silhuetas laterais + vista de cima (SVG)
  scripts/               # install, kiosk, pair-elm327, generate-bodies, …
  systemd/               # serviço e autostart do kiosk
  data/                  # trips.sqlite, vehicle-state.json, vehicles/ (fotos)
```


## Câmeras e visão 360°

Até quatro câmeras USB/UVC (`/dev/video0` …) mais uma de ré. O backend
entrega MJPEG em `/api/cameras/{id}/stream`. Se o dispositivo não existe
(simulador, ou câmera desconectada), o painel gera um feed de teste.

- Prefira câmeras que falem **MJPEG nativo** (menos CPU no Pi 4). FPS
  padrão 12, JPEG qualidade 55 — ajuste em `config.yaml` → `cameras`.
- Câmera de ré analógica: use um dongle **AV→USB**. Hub **alimentado**
  é quase obrigatório com várias câmeras + GPS + dongle CarPlay.
- Sinal de ré: `cameras.reverse_gpio` (BCM, ex. 17). O software tenta
  `gpiod` e cai no sysfs. `reverse_active_low: true` se o sensor for
  ativo em 0 V. Dá para forçar pelo hook `POST /api/cameras/reverse?value=true`.
- **360° bird’s-eye**: é um esboço. A costura real precisa de calibração
  no carro (tabuleiro xadrez). Rode, com as quatro câmeras no lugar:

```bash
source .venv/bin/activate
# gera data/birdseye/<id>.json com a homografia de cada câmera
python3 scripts/calibrate-birdseye.py --camera front --device /dev/video0
python3 scripts/calibrate-birdseye.py --camera rear  --device /dev/video1
python3 scripts/calibrate-birdseye.py --camera left  --device /dev/video2
python3 scripts/calibrate-birdseye.py --camera right --device /dev/video3
```

Sem esses JSON a página 360° mostra um placeholder. Mesmo calibrado, o
resultado depende da posição das câmeras e não substitui um sistema 360
comercial.

## Mídia, Bluetooth e equalizador

Coloque MP3/FLAC/OGG/M4A em `data/music/` (há três faixas de demonstração).
O player usa `mpv` ou `ffplay` se existirem; o volume tenta `wpctl`
(PipeWire), depois `pactl`, depois `amixer`.

Bluetooth A2DP sink + AVRCP passa pelo BlueZ (`busctl` / D-Bus
`org.bluez.MediaPlayer1`). No simulador a fonte Bluetooth é mock.

O equalizador de 5 bandas (60 Hz, 230 Hz, 910 Hz, 4 kHz, 14 kHz) fica em
`media.eq` e na tela Música. Sem um plugin de EQ no PipeWire/ALSA a UI
guarda o estado e tenta aplicar no `mpv` quando possível — no Pi “pelado”
trate como ajuste visual + dica de configuração de áudio.

## Telefone mãos-livres (HFP / PBAP)

No carro o caminho suportado é **oFono** em cima do BlueZ:

```bash
sudo apt-get install ofono ofono-phonesim bluez pulsemodule-bluetooth
# pareie o celular no bluetoothctl; o perfil HFP deve aparecer no oFono
```

A agenda tenta PBAP (Phonebook Access) via oFono/obex. Sem oFono no ar
(é o caso do simulador), a tela usa uma agenda e um registro de exemplo,
e o botão **Simular chamada** exercita o overlay de atender/encerrar.

## CarPlay / Android Auto (dongle Carlinkit)

O painel **não** reimplementa o protocolo da Apple ou do Google. Ele
detecta o dongle USB (IDs acima), lança o driver open-source e devolve o
foco ao dashboard pelo botão Voltar.

```bash
# no Pi, com internet, clona node-CarPlay / react-carplay em vendor/
./scripts/install-carplay.sh
# o kiosk já está no DISPLAY=:0; o script de lançamento usa o mesmo display
# (scripts/carplay-launch.sh). O tile CarPlay chama POST /api/carplay/launch
```

Fluxo: no Início, toque em **CarPlay** (tela cheia, barra superior com
← Painel). Se o dongle e o driver estiverem prontos, **Abrir dongle**
sobe o Electron/npm do react-carplay por cima do kiosk. **← Painel**
manda SIGTERM no processo e volta ao lançador. Sem hardware a grade de
apps é um mock, suficiente para desenvolver a UI.

### Áudio e microfone (CarPlay e chamadas)

- Saída: DAC USB, HDMI da tela ou jack/aux. No PipeWire, crie um loop ou
  defina o sink padrão (`wpctl set-default <id>`) para o processo do
  driver e para o `mpv` da rádio/música não brigarem.
- Microfone: um USB simples no Pi. No react-carplay / node-CarPlay,
  selecione o device de captura no Pulse/PipeWire (`wpctl status`,
  `wpctl set-default` na source). Para HFP, o oFono + `ofono-phonesim`
  ou o módulo HFP do Pulse/PipeWire roteia o SCO; isso costuma exigir
  um firmware Bluetooth decente no Pi (USB dongle BT 5 às vezes vai
  melhor que o rádio interno).
- Enquanto o CarPlay está em tela cheia, pause a mídia local para não
  misturar duas saídas. O volume da central continua valendo se os
  dois processos apontarem para o mesmo sink.

Projetos de referência: [node-CarPlay](https://github.com/rhysmorgan134/node-CarPlay)
e [react-carplay](https://github.com/rhysmorgan134/react-carplay). A
instalação e as versões mudam — o script só clona e roda `npm install`.

## Rádio FM (RTL-SDR, opcional)

Com um dongle RTL2832U e o `rtl_fm` (`sudo apt-get install rtl-sdr`):

```yaml
media:
  fm:
    enabled: true
    mhz: 90.5
```

O backend sintoniza a frequência (76–108 MHz) e manda o áudio para a
saída padrão do sistema. Sem o dongle, a tela FM continua navegável
(presets, slider) mas o som de verdade vem do **rádio online** da mesma
página (CBN, Jovem Pan, BandNews, USP — URLs no `config.yaml`).


## App companheiro no celular (PWA)

No mesmo Wi-Fi do Pi (ou no hotspot que o Pi emite), abra:

```
http://<IP-DO-PI>:8080/app
```

O Chrome/Safari oferece **Adicionar à tela inicial** (manifest + service worker). PIN padrão: `2016` — troque em `companion.pin` ou na variável `PAINEL_COMPANION_PIN` (o alias `LANCER_COMPANION_PIN` ainda vale). No app você escolhe o perfil, a pintura, as 3–5 fotos candidatas, envia uma arte própria e ajusta as zonas de farol/roda.

### Hotspot Wi-Fi no próprio Pi

**NetworkManager** (Raspberry Pi OS recente):

```bash
sudo nmcli dev wifi hotspot ifname wlan0 ssid PainelTFT password "escolha-uma-senha"
# o Pi costuma ficar em 10.42.0.1
# no celular: http://10.42.0.1:8080/app
```

**hostapd + dnsmasq** (caminho clássico): instale os dois pacotes, configure
`/etc/hostapd/hostapd.conf` com `ssid=LancerPainel` e uma senha WPA2, e o
dnsmasq entregando `10.42.0.1/24` em `wlan0`. O painel já escuta em `0.0.0.0:8080`.
No carro, lembre que o adaptador Bluetooth do ELM327 e o Wi-Fi do Pi 4
dividem antena — um dongle Wi-Fi USB ajuda se a rede oscilar.

## Perfis de veículo, VIN e arte do carro

Tudo que é específico de um modelo mora em `profiles/*.yaml` (tanque, tipo
de câmbio e relações, pneus, diferencial, faixa vermelha, combustível/AFR,
revisões, DIDs da CVT, PIDs extras). O arquivo `_default.yaml` é a base;
os outros só declaram o que muda. Exemplos inclusos:

- `lancer-2016-cvt` — Mitsubishi Lancer HL 2016, sedã, CVT Jatco
- `onix-2022-hatch` — Chevrolet Onix, hatch flex
- `compass-2021-suv` — Jeep Compass
- `hilux-2022-pickup` — Toyota Hilux, diesel
- `generic-coupe` / `generic-wagon` — cupê e perua genéricos

Na primeira partida um **assistente** (`?setup=1` força a tela) pede para
detectar ou escolher o perfil e a cor. A escolha fica em
`data/vehicle-state.json`. No `config.yaml`, `profile: auto` tenta casar
sozinho depois do VIN.

### VIN

Na partida o painel pede o VIN por **OBD Mode 09 PID 02**. A decodificação
é offline (tabela WMI com marcas brasileiras e do exterior, ano, dígito
verificador, dicas de modelo). Se houver internet, há um lookup opcional no
**NHTSA vPIC** (`DecodeVinValues`), com cache em `data/vin-cache.json`.
O resultado vira tipo de carroceria (sedã/hatch/SUV/picape/cupê/perua) e, se
possível, um perfil. Clones ELM327 v2.1 frequentemente **não** respondem
Mode 09 — aí vale a escolha manual no assistente ou no app. O vPIC também
é fraco em alguns VIN brasileiros (WMI 9C9/93Y etc.); o fallback offline
cobre o Lancer e os outros exemplos.

### Ilustração de fallback (v0.4.0)

A reserva lateral de cada tipo de carroceria (sedã, hatch, SUV, picape,
cupê, perua) é uma **ilustração genérica gerada por IA**, sem marcas
oficiais, já recortada em PNG transparente (`app/static/img/bodies/<tipo>.png`).
As rodas são detectadas e gravadas em `<tipo>.json` para os overlays de
giro, farol e lanterna alinharem com a silhueta (recortados via
`mask-image`). A pintura do tema (`--car-paint`) entra como um véu CSS
(`mix-blend-mode: color`) sobre o grafite da ilustração.

Os SVG laterais antigos e as vistas de cima (`<tipo>-top.svg`) continuam
no pacote: o topo segue vetorial na tela de câmera 360, e o SVG lateral
só é usado se o PNG daquele tipo estiver ausente.

### Foto real do modelo (opcional)

Depois do VIN (ou do perfil), o painel busca no **Wikimedia Commons**
(`'<ano> <marca> <modelo>'`, preferindo perfil lateral, licenças livres).
A foto é baixada **uma vez**, o fundo é removido, a orientação é normalizada
(carro olhando para a esquerda) e o PNG + a ficha (autor, licença, URL,
zonas) ficam em `data/vehicles/<chave>/`. Depois funciona offline, com os
créditos em texto pequeno na página Carro.

Instalação no Pi (opcional, só para o recorte de fundo e a detecção das
rodas). O código usa o modelo **u2netp (~5 MB)**, não o bria de ~1 GB:

```bash
source .venv/bin/activate
pip install rembg onnxruntime opencv-python-headless numpy
```

Na primeira foto o `u2netp.onnx` é baixado para `~/.u2net` / `~/.rembg`.
Sem o rembg, a foto entra com o fundo original. Sem o OpenCV, as rodas
usam uma heurística (18 % / 82 % da silhueta). As zonas de farol, lanterna
e roda também podem ser ajustadas à mão no app do celular. O app lista as
**3 a 5 melhores candidatas** para você escolher.

Provedor reserva (opcional, com chave):

```yaml
car_photo:
  enabled: true
  fallback_provider: unsplash   # só se o Commons não achar nada
  api_key: "…"                  # ou PAINEL_PHOTO_KEY / LANCER_PHOTO_KEY
```

Você também pode enviar um PNG/SVG próprio (lateral e/ou topo) pelo app.

## Autonomia até o posto

1. Combustível restante: `PID 0x2F` (nível %) × `fuel.tank_liters` (50 L no
   Lancer, configurável). Se a ECU não expõe 0x2F, use **Marcar tanque cheio**
   no app e o gasto passa a ser integrado pelo MAF.
2. Consumo: janela rolante (~15 min), ponderada cidade (&lt; 50 km/h) /
   estrada. Se ainda não houver janela, usa a média da viagem ou 9,5 L/100 km.
3. Postos: OpenStreetMap via Overpass (`amenity=fuel`), com cache em
   `data/stations-cache.json` para uso offline. No simulador os postos são
   fictícios ao redor da Av. Paulista (não chamamos a API).
4. Rota no mapa já existente (não há Waze):
   - **OSRM** público (`https://router.project-osrm.org`) — distância e
     duração, **sem** trânsito ao vivo. Você pode apontar `range.osrm_url`
     para um OSRM próprio.
   - **TomTom** ou **HERE** se houver chave (faixa gratuita): duração com
     trânsito, e um acréscimo de consumo nos minutos extras
     (`fuel.idle_l_per_min`, padrão 0,025 L/min, típico de 2.0 em marcha lenta
     / anda-e-para).
5. Cada posto mostra distância, ETA, litros estimados na chegada e um selo
   **ALCANCE** / **NO LIMITE** / **FORA**. Um alerta de autonomia baixa
   sugere o posto alcançável mais perto.

Sem internet ou sem chave, a UI avisa claramente e usa só o consumo médio
(e, se preciso, a distância estimada).

### Como obter uma chave de trânsito

- **TomTom**: crie conta em https://developer.tomtom.com/ , crie um app e
  copie a chave da Routing API. No `config.yaml`:

  ```yaml
  range:
    routing: tomtom
    tomtom_key: "SUA_CHAVE"
  ```

  Ou `LANCER_TOMTOM_KEY`. A chamada usa `traffic=true`.

- **HERE**: https://developer.here.com/ , Routing v8, `departureTime=now`.

  ```yaml
  range:
    routing: here
    here_key: "SUA_CHAVE"
  ```

  Ou `LANCER_HERE_KEY`.

As faixas gratuitas têm cota diária — no carro o painel só consulta de
tempos em tempos e quando você abre Postos / Atualizar.


## Desempenho, pista, IMU, dash cam, saúde, LEDs, TPMS e valet

Tudo isso roda no simulador (com mocks) e no carro, com o tema vermelho e o
`performance_mode` para o Pi 4. Os dados ficam em `data/sport.sqlite`.

### Cronômetro de desempenho

Mede automaticamente **0–100 km/h**, **80–120**, **402 m (1/4 de milha)** e
**100–0** (frenagem). A velocidade é a fusão GPS + OBD: se o GPS está
fresco (&lt; 0,4 s) e com pelo menos 4 satélites, ele pesa 70 %; o OBD
ancora o viés. Os melhores tempos entram no histórico.

O GPS a **10 Hz** ajuda muito nas arrancadas. Com um u-blox, rode
`scripts/ublox-10hz.sh /dev/ttyACM0` depois do `gpsd`. O script envia
`UBX-CFG-RATE` com `measRate=100` ms e tenta 115200 baud. No simulador,
o botão **Arrancada (sim)** dispara um sprint 0–130 e depois 100–0.

### Modo pista

Defina a linha de largada/chegada com **Portão aqui** (posição GPS atual)
ou tocando no mapa / coordenadas via API. O painel detecta a passagem,
conta voltas, setores, mostra o **delta ao vivo** vs. a melhor volta na
mesma distância e guarda o traçado e as sessões.

### G-meter e IMU

Com MPU-6050 / MPU-9250 / ICM-20948 no I2C, o círculo de atrito usa a
aceleração real (X frente, Y direita, Z cima). Sem IMU — ou com
`imu.force_gps: true` — o G longitudinal vem da derivada da velocidade e
o lateral de `v × ω` (rumo do GPS). Calibre parado e nivelado
(`scripts/imu-calibrate.py` ou o botão na tela).

### Telemetria e dash cam

A telemetria grava RPM, velocidade fundida, acelerador, temperaturas, G e
GPS na taxa configurável (`telemetry.hz`, padrão 10). A revisão tem
gráfico (velocidade, RPM e |G|) e exportação **CSV**.

A dash cam usa **ffmpeg** na câmera escolhida, com overlay de velocidade,
RPM, G e GPS. A gravação é em loop com teto de armazenamento
(`dashcam.max_gb`); um |G| acima do limite ou o botão **Proteger**
impedem que aquele clipe seja apagado. Sem câmera ou sem ffmpeg, o
simulador gera um clipe stub para testar o navegador de clipes. Um SSD
maior é recomendado.

### Shift light

Pontos de RPM configuráveis (úteis no modo Sport / manual da CVT). A
barra do topo acende conforme os pontos; beep ou voz (`espeak-ng`, pt-BR)
saem pelo áudio. Ajuste na tela Desempenho ou em `shift.rpm_points`.

### Saúde do carro

Hodômetro: você informa o km atual (do cluster original) e o painel soma
a distância GPS/OBD. Lembretes de óleo, fluido do CVT, filtros, pneus,
fluido de freio e velas — por km e por tempo. Histórico de DTC (além da
página Falhas). Bateria: registra a **queda de tensão na partida** e a
tendência em repouso, com aviso antecipado (queda alta ou repouso
&lt; 12,2 V). No simulador há uma partida com queda típica (~10,8 V) e
uma tendência de demonstração.

### LEDs ambiente

Fita WS2812 ou WS2815 via `rpi_ws281x` no **GPIO 18**. Use **transmissor
de nível 3V3→5V** e **fonte 5 V dedicada** (ou, no WS2815, 12 V na fita e
5 V só na lógica), com GND comum. Modos: RPM, música (nível de áudio),
alertas (pisca no vermelho) ou cor fixa. Controle no painel ou no app
`/app`. Sem a biblioteca, a tela mostra um preview.

### TPMS

Sensores BLE externos baratos: o painel interpreta anúncios comuns
(pressão em kPa ou PSI, temperatura, bateria) e mostra as quatro rodas na
página **Carro**, com alerta de pressão baixa / temperatura / bateria do
sensor. No simulador as pressões são mockadas (~220 kPa). No carro, instale
`bleak`, coloque `tpms.simulate: false` e vincule o id de cada sensor à
roda (`fl` `fr` `rl` `rr`).

### Modo valet

PIN próprio (padrão `1234`, troque — é independente do PIN do app
`companion.pin`, que é `2016`). Ao travar, mídia, telefone, CarPlay, rádio
e ajustes ficam bloqueados. O painel registra velocidade máxima, rastro e
eventos bruscos (aceleração, frenagem, curva). Ao destravar com o PIN,
aparece o relatório.

### Dependências opcionais no Pi

```
# no venv do painel, só no Raspberry Pi:
pip install smbus2 rpi_ws281x bleak
# dash cam e overlay:
sudo apt install ffmpeg
# voz do shift light (opcional):
sudo apt install espeak-ng
```

## Licença

Código deste painel: MIT. Os tiles do OpenStreetMap pertencem aos
contribuidores da OSM (ODbL). Use cache próprio e evite martelar os
servidores de tile em produção. As fotos de veículos vêm do Wikimedia
Commons (ou do provedor reserva que você configurar) e **mantêm a licença
e os créditos do autor** — eles aparecem na página Carro e em
`data/vehicles/<chave>/meta.json`. As ilustrações de fallback laterais são genéricas (geradas por IA, sem marcas); as vistas de cima em SVG são originais
deste projeto e não reproduzem logotipos oficiais.
