# Lista de compras — Painel TFT v0.4.3

Preços conferidos em **13 de novembro de 2026** (fuso **America/Sao_Paulo**), em páginas de produto que abriram com sucesso. Valores em **reais (BRL)**, como exibidos na ficha — quando a loja mostra Pix/à vista e cartão, os dois aparecem. Frete, impostos de importação e cupons **não** entram nos totais.

O Mercado Livre redirecionou para verificação de conta neste ambiente, o HTML da Amazon.com.br não pôde ser lido de forma confiável e a Magazine Luiza devolveu 403. **Não há preço inventado** desses marketplaces. A FilipeFlop opera como [MakerHero](https://www.makerhero.com/) (revendedora oficial Anatel). Eletrogate e Baú da Eletrônica bloquearam o acesso.

Duas cestas:

- **Básico** — o mínimo para o HUD ligar no carro com OBD de verdade, GPS e o mapa. Mantém o **Raspberry Pi 4 4 GB**: já dá conta desse recorte (com `performance_mode` se o frame rate apertar), esquenta menos no painel fechado e custa menos.
- **Final** — a experiência completa do v0.4.3 (HUD wireframe com telltales de marcha e luzes, WebGL, CarPlay, câmeras, IMU, LEDs, etc.). Troca a placa do Básico por um **Raspberry Pi 5 4 GB**, com cooler ativo oficial e fonte oficial 27 W (bancada), e soma o restante. O total Final **já inclui** o Básico, com essa substituição da placa.

O ELM327 v2.1 Bluetooth que você já tem entra como **R$ 0**.

## Por que Pi 4 no Básico e Pi 5 no Final

O HUD 0.4.3 desenha o carro em WebGL (anéis + herói 2D no Lancer, modelo 3D nos outros perfis) dentro do Chromium em 800×480, visando 30+ fps. No **Básico** isso roda com OBD + GPS + mapa, sem CarPlay nem câmeras: o Pi 4 4 GB basta.

No **Final** entram ainda o dongle CarPlay (node-CarPlay), câmeras USB, áudio e, se houver, RTL-SDR. Aí o **Pi 5 4 GB** se justifica: CPU bem mais rápida e GPU VideoCore VII, que aliviam o kiosk com WebGL + CarPlay. A diferença no Pix para o Pi 4 4 GB é de **R$ 131,10**. O Pi 5 8 GB está em estoque, mas sai **R$ 907,25** a mais no Pix que o 5 4 GB — só vale se você for empilhar várias câmeras MJPEG ao mesmo tempo; não entra no total padrão.

O Pi 5 esquenta mais e, sem cooler, reduz o relógio. A cesta Final leva o **cooler ativo oficial**. A fonte oficial **27 W (5 V / 5 A, USB-C PD)** é a certa na bancada (gravação do cartão, testes). No carro ela não serve (é 100–240 V AC): use o mesmo buck automotivo 9–36 V → 5 V 5 A do Básico, com cabo USB-A → USB-C curto e de boa bitola, e ligue `usb_max_current_enable=1` no EEPROM do Pi 5 para ele aceitar 5 A sem negociação PD. A case oficial do Pi 5 (dissipador + cooler, R$ 85,40 no Pix, em estoque) é **alternativa** ao cooler ativo — os dois não se encaixam juntos; o cooler ativo refrigera melhor, a case protege melhor. O total usa o cooler ativo, como pedido.

## Kit Básico — HUD com OBD real, GPS e mapa

| Qtd | Item | Loja (link da ficha) | Preço como exibido | Estoque | Nota |
| --- | --- | --- | --- | --- | --- |
| 1 | Raspberry Pi 4 Model B 4 GB Anatel | [MakerHero](https://www.makerhero.com/produto/raspberry-pi-4-model-b/?attribute_pa_memoria=4gb) | R$ 1.365,05 no Pix (R$ 1.436,90 no cartão, 3× de R$ 478,97) | Em estoque | Placa avulsa, homologada Anatel. Suficiente para o HUD + OBD + GPS + mapa. |
| 1 | Tela 7" HDMI touch 800×480 | [Smartkits](https://www.smartkits.com.br/display-lcd-7-hdmi-touchscreen-800x480-para-raspberry-pi) | R$ 493,91 à vista (R$ 519,90) | Disponibilidade imediata | HDMI + USB para o toque; brilho anunciado 250 nits (no sol forte pode ficar apagada). Acompanha cabos HDMI e USB, mas o HDMI da tela pode não ser micro HDMI — leve o cabo micro HDMI abaixo. A ficha **não lista saída de áudio/P2**. |
| 1 | Case oficial Raspberry Pi 4 (preta ou branca) | [MakerHero](https://www.makerhero.com/produto/case-raspberry-pi-4-oficial/) | R$ 37,90 no Pix (R$ 39,90; de R$ 49,90) | Em estoque nas duas cores | Encaixe oficial. |
| 1 | Cooler oficial para a case oficial do Pi 4 | [MakerHero](https://www.makerhero.com/produto/cooler-para-case-oficial-raspberry-pi-4/) | R$ 36,00 no Pix (R$ 37,90; de R$ 41,90) | Em estoque | Combina com a case oficial. Carro parado no sol esquenta. |
| 1 | Conversor buck 9–36 V → 5 V 5 A, saída USB | [Smartkits](https://www.smartkits.com.br/modulo-conversor-step-down-p-saida-usb-5v-5a) | R$ 32,90 | Disponibilidade imediata | Entrada 9–36 V DC, 5 V fixa até 5 A, conector USB-A. Ligar no **ACC/ignição**, com fusível, nunca direto na bateria sem corte. Não é módulo automotivo “pronto” com filtro pesado de alternador. |
| 1 | Módulo de retardo NE555 com relé 12 V 10 A | [Smartkits](https://www.smartkits.com.br/modulo-de-retardo-ne555-com-releq-12v-10a) | R$ 14,90 | Disponibilidade imediata | Mantém o 12 V um tempo depois de cortar o ACC para o Pi desligar com segurança. Se quiser o aviso por GPIO do README, complete com um divisor/módulo de ignition-sense. |
| 1 | Cabo USB-A → USB-C 1 m | [Smartkits](https://www.smartkits.com.br/cabo-usb-tipo-c-1m) | R$ 9,90 | Disponibilidade imediata | Liga a saída USB-A do buck na entrada USB-C do Pi. Prefira cabo curto e de boa bitola (3–5 A). |
| 1 | Cabo micro HDMI → HDMI 1,50 m | [MakerHero](https://www.makerhero.com/produto/cabo-micro-hdmi-150-metros/) | R$ 18,90 no Pix (R$ 19,90; de R$ 29,90) | Em estoque | Necessário no Pi 4/5 (saída micro HDMI). Mais barato hoje que o equivalente da RoboCore (R$ 24,15 no Pix, 575 un.). |
| 1 | microSD 64 GB SanDisk Extreme Pro A2 (SDSQXCU-064G-GN6MA) | [KaBuM!](https://www.kabum.com.br/produto/482190/cartao-micro-sd-sandisk-extreme-pro-64gb-uhs-i-com-adaptador-200mb-s-leitura-e-90mb-s-gravacao-sdsqxcu-064g-gn6ma) | R$ 277,43 no Pix (R$ 308,26 no cartão; de R$ 555,54) | Em estoque (6 un.), vendido e entregue pela KaBuM! | Classe A2, adequado ao sistema do Pi. |
| 1 | GPS u-blox NEO-M8N V2 com antena (até 10 Hz, UART) | [Smartkits](https://www.smartkits.com.br/modulo-gps-neo-m8n-v2-com-antena) | R$ 113,91 à vista (R$ 119,90) | Disponibilidade imediata | GPS confirmado para o mapa e para o cronômetro (`scripts/ublox-10hz.sh`). É **UART/TTL**, não USB: liga na UART do Pi (3,3 V) ou num conversor USB–TTL. O dongle USB VK-172 da consulta anterior **não teve preço reconfirmado hoje** (veja itens sem preço). |
| 1 | Tap de fusível lâmina Mini Technoise (pacote com 10, cód. 13688) | [Eletroking](https://www.eletroking.com.br/tap-adaptador-de-fusivel-mini-technoise-pacote-c-10-13688) | R$ 123,20 | Disponibilidade imediata | Você só precisa de 1–2 peças; unidade avulsa não foi encontrada com preço confirmado. **Confira na caixa de fusíveis** se o perfil é Mini (ATM) — comum no habitáculo do Lancer 2016 — ou Médio. O pacote Médio (cód. 13689) está na mesma loja por R$ 123,10: [ficha](https://www.eletroking.com.br/tap-adaptador-de-fusivel-medio-technoise-pacote-c-10-13689). |
| 1 | Módulo RTC DS3231 | [Smartkits](https://www.smartkits.com.br/modulo-rtc-ds3231) | R$ 24,90 | Disponibilidade imediata | Útil no carro: o Pi perde o relógio quando fica sem energia e sem rede. I2C (mesmo barramento da IMU). A versão “para Raspberry Pi” da MakerHero estava **fora de estoque**. |
| 1 | ELM327 Bluetooth clone v2.1 | — (já possui) | R$ 0 | — | **Já é seu.** Serve para começar (~3–8 PIDs/s, PIN típico 1234). |

### Total do kit Básico (Pix/à vista)

**R$ 2.548,90** — Pi 4 4 GB + tela Smartkits + case e cooler oficiais + buck 5 A + relé de retardo + cabos USB-C e micro HDMI + microSD 64 GB A2 + GPS NEO-M8N + pacote de taps Mini + RTC DS3231 + ELM327 já seu.

Sem o pacote de 10 taps (se você já tiver como puxar o ACC com fusível), o subtotal fica **R$ 2.425,70**. Frete não incluído. Suporte veicular para a tela 7" ficou **sem preço confirmado** (veja o final).

## Kit Final — experiência completa (inclui o Básico)

O Final **substitui** a placa do Básico (Pi 4 4 GB + case oficial + cooler da case) pelo pacote Pi 5 abaixo, **mantém** tela, buck automotivo, relé, cabos, microSD, GPS NEO-M8N, taps, RTC e o ELM já seu, e **soma** os extras.

### Troca da placa (não some com o Pi 4)

| Qtd | Item | Loja (link da ficha) | Preço como exibido | Estoque | Nota |
| --- | --- | --- | --- | --- | --- |
| 1 | Raspberry Pi 5 Model B 4 GB Anatel | [MakerHero](https://www.makerhero.com/produto/raspberry-pi-5-model-b-anatel/) | R$ 1.496,15 no Pix (R$ 1.574,90 no cartão, 3× de R$ 524,97) | Em estoque (variante 4 GB) | Placa do Final. A variante 2 GB está fora de estoque; a 16 GB também. |
| 1 | Cooler ativo oficial Raspberry Pi 5 | [MakerHero](https://www.makerhero.com/produto/cooler-raspberry-pi-5-oficial/) | R$ 40,75 no Pix (R$ 42,90; de R$ 49,90) | Em estoque | Dissipador + ventoinha oficiais, pasta já aplicada. Necessário para o Pi 5 no painel com WebGL/CarPlay. **Não combina** com a case oficial. |
| 1 | Fonte oficial Raspberry Pi 5 27 W (USB-C PD) | [MakerHero](https://www.makerhero.com/produto/fonte-raspberry-pi-5-oficial/) | R$ 109,15 no Pix (R$ 114,90; de R$ 129,90) | Em estoque (branca ou preta) | 5,1 V / 5 A com Power Delivery — use **na bancada**. No carro, o buck 5 V 5 A do Básico + cabo USB-C, com `usb_max_current_enable=1`. |
| — | *(alternativa, não entra no total)* Raspberry Pi 5 8 GB Anatel | [MakerHero](https://www.makerhero.com/produto/raspberry-pi-5-model-b-anatel/) | R$ 2.403,40 no Pix (R$ 2.529,90 no cartão) | Em estoque | +R$ 907,25 no Pix em relação ao 5 4 GB. Só se for empilhar várias câmeras. |
| — | *(alternativa ao cooler ativo, não some com ele)* Case oficial Raspberry Pi 5 | [MakerHero](https://www.makerhero.com/produto/case-raspberry-pi-5-oficial/) | R$ 85,40 no Pix (R$ 89,90; de R$ 99,90) | Em estoque (preta ou branca) | Já traz dissipador e cooler. Melhor proteção; troca o cooler ativo, não se empilha. |

### Extras do Final (além do Básico já substituído)

| Qtd | Item | Loja (link da ficha) | Preço como exibido | Estoque | Nota |
| --- | --- | --- | --- | --- | --- |
| 1 | Módulo CAN MCP2515 + TJA1050 (não é HAT pronto) | [Smartkits](https://www.smartkits.com.br/modulo-can-bus-mcp2515) | R$ 14,90 | Disponibilidade imediata | SPI no GPIO do Pi; CAN-H/CAN-L nos pinos 6 e 14 do OBD2 + GND. Lê marcha e alguns sinais com `gear_source: can` / luzes via CAN. A ficha equivalente da MakerHero estava fora de estoque. |
| 2 | Isolador óptico PC817 2 canais 3,6–24 V | [UsinaInfo](https://www.usinainfo.com.br/optoacoplador/isolador-optico-pc817-2-canais-36-24v-8305.html) | R$ 11,34 no Pix/boleto (R$ 11,94 no cartão) **cada** | Em estoque | Dois módulos = 4 canais (farol, seta esquerda, seta direita, lanterna ou freio de mão), como no README. O módulo de 4 canais da mesma loja estava **fora de estoque** (previsão 10/12/2026). O módulo da MakerHero também estava zerado; o CI avulso PC817 dela está em estoque a R$ 0,85 no Pix, mas exige resistor e protoboard. |
| 1 | Dongle Carlinkit CCPA200 (CarPlay / Android Auto USB) | [KaBuM! (marketplace MANLAI)](https://www.kabum.com.br/produto/997701/carlinkit-ccpa200-adaptador-carplay-android-auto-sem-fio) | R$ 363,84 no Pix (R$ 382,99 no cartão, 10× de R$ 38,29) | Em estoque | Família CPC200-CCPA do README (IDs USB típicos `1314:1520/1521/1522`). Sem o dongle, a tela CarPlay é só um mock. Conferir no anúncio se é a revisão compatível. |
| 1 | Câmera de ré analógica Permak 2x1 universal | [Eletroking](https://www.eletroking.com.br/alarme-e-seguranca/camera-de-re-permak-2x1-universal) | R$ 60,90 | Disponibilidade imediata | Câmera de para-choque (12 V, CVBS). Precisa do capturador USB abaixo para o Pi. Kits 360 **sem ficha com preço confirmado**. |
| 1 | Placa de captura USB EasyCAP (AV/CVBS → UVC) | [KaBuM! (marketplace AO VENTO)](https://www.kabum.com.br/produto/613842/placa-de-captura-usb-easycap-de-vhs-vhs-vcr-tv-para-digital) | R$ 131,42 | Disponível (marketplace) | Entra a câmera de ré analógica no painel como UVC. Vendedor de marketplace: confira a ficha na hora da compra. |
| 1 | Webcam USB Logitech C270 720p (UVC, microfone embutido) | [KaBuM!](https://www.kabum.com.br/produto/37697/webcam-hd-logitech-c270-720p-30-fps-microfone-integrado-usb-2-0-960-000694) | R$ 199,99 no Pix (R$ 235,28 no cartão; de R$ 258,81) | Em estoque (23 un.), vendida pela KaBuM! | Dash cam / cabine. Para mais ângulos, some outra C270 (+R$ 199,99) — não entra no total. Não substitui a câmera de ré externa. |
| 1 | Headset USB Logitech H390 (microfone com redução de ruído) | [KaBuM!](https://www.kabum.com.br/produto/95485/headset-com-fio-usb-logitech-h390-com-almofadas-controles-de-audio-integrado-e-microfone-com-reducao-de-ruido-981-000014) | R$ 219,99 no Pix (R$ 258,81 no cartão) | Em estoque (22 un.), vendido pela KaBuM! | Microfone para CarPlay/HFP. Microfones de mesa gamer são pouco práticos no painel; lapela USB barata não teve ficha confirmada em estoque (a JBL wireless saía R$ 621,99 — fora da conta). A C270 já tem mic, mas o H390 é bem melhor para ligação. |
| 1 | IMU MPU-6050 (I2C, 6 eixos) | [MakerHero](https://www.makerhero.com/produto/acelerometro-e-giroscopio-3-eixos-6-dof-mpu-6050/) | R$ 21,75 no Pix (R$ 22,90) | Em estoque | VCC 3V3, SDA pino 3, SCL pino 5, endereço 0x68; calibre com `scripts/imu-calibrate.py`. |
| 1 | Fita LED WS2812B 5050, 1 m (5 V) | [RoboCore](https://www.robocore.net/led/fita-de-led-rgb-ws2812-5050-1m) | R$ 56,90 | 22 un. em estoque | GPIO 18 (PWM0). **Não** alimentar pelo 5 V do Pi; GND comum. Versão com silicone (melhor no carro): R$ 59,76 no Pix, 42 un.: [ficha](https://www.robocore.net/display-led/fita-de-led-rgb-ws2812-5050-com-silicone-1m). |
| 1 | Conversor de nível 3,3–5 V bidirecional (8 canais) | [Smartkits](https://www.smartkits.com.br/modulo-conversor-de-nivel-logico-3-3-5v-bidirecional-8-canais) | R$ 10,90 | Disponibilidade imediata | O README prefere 74AHCT125 (não encontrado nesta consulta); este módulo serve. |
| 1 | Segunda unidade do buck 5 V 5 A (fonte dedicada da fita) | [Smartkits](https://www.smartkits.com.br/modulo-conversor-step-down-p-saida-usb-5v-5a) | R$ 32,90 | Disponibilidade imediata | Mesmo módulo do Básico, só para a fita LED. Evita puxar a corrente dos LEDs no buck do Pi. |
| 1 | Hub USB 2.0 de 4 portas | [MakerHero](https://www.makerhero.com/produto/hub-usb-2-0-com-4-portas/) | R$ 28,40 no Pix (R$ 29,90; de R$ 35,90) | Em estoque | Ajuda a espalhar GPS/UART-USB, dongle CarPlay, capturador e mic. **Não é alimentado por fonte própria** — o ideal para várias câmeras MJPEG é um hub USB 3.0 com fonte; esse não teve ficha confirmada hoje (veja itens sem preço). |

O GPS 10 Hz já está no Básico (NEO-M8N). Não há segunda unidade no Final.

### Total do kit Final (Pix/à vista, já inclui o Básico com a troca da placa)

**R$ 3.920,57**

Conta: Básico R$ 2.548,90 − Pi 4 4 GB − case − cooler da case (R$ 1.438,95) + Pi 5 4 GB + cooler ativo + fonte 27 W (R$ 1.646,05) + extras (R$ 1.164,57).

Se trocar o Pi 5 4 GB pelo 8 GB, some **R$ 907,25** → **R$ 4.827,82**. Se quiser mais uma C270, some **R$ 199,99**. Frete não incluído.

## Itens pedidos que ficaram sem preço confirmado (não entram nos totais)

Estes apareceram na busca ou na ficha, mas a página não abriu com preço/estoque confiável, estava fora de estoque, ou o anúncio estava pausado. **Nenhum valor foi inventado.**

- **Dongle GPS USB VK-172** — a ficha da Magazine Luiza da consulta anterior devolveu 403 hoje; no Mercado Livre o anúncio da RoboBuilders estava **pausado**, sem preço visível. Por isso o Básico usa o NEO-M8N (UART), já confirmado.
- **Suporte veicular para a tela 7"** — não houve ficha de suporte de painel/ventosa para 7" com preço lido (KaBuM devolveu itens irrelevantes ou 429; Mercado Livre inacessível). O README também sugere um suporte impresso em 3D.
- **Hub USB 3.0 alimentado (com fonte própria)** — o recomendado para CarPlay + câmeras + capturador; só foi confirmado o hub 2.0 *sem* fonte da MakerHero, já no Final.
- **Caixa de som USB / DAC / amp** — a tela 7" da Smartkits **não lista saída de áudio** na ficha. A [BrazilPC BPC-D02L](https://www.kabum.com.br/produto/185076/caixinha-de-som-brazilpc-bpc-d02l-para-computador-3w-x-2-rms-usb-preto) continua **fora de estoque** (R$ 65,78 / R$ 69,98 na ficha, vendedor Alphaprime). Outras caixinhas USB na KaBuM apareciam com quantidade 0. Sem ela, o som do CarPlay/rádio precisa do AUX do som do carro ou de um DAC/caixa ainda não confirmados.
- **Kit de câmeras 360** — nenhuma ficha de kit 360 com preço confirmado. O caminho confirmado é câmera de ré analógica + EasyCAP + (opcional) C270 extras.
- **Sensores TPMS BLE (4 válvulas)** — o que o painel lê via `bleak`. Sem ficha carregável de kit BLE; muitos “TPMS sem fio” usam 433 MHz com display próprio, incompatíveis.
- **Dongle RTL-SDR (RTL2832U)** — há anúncios no Mercado Livre (ex.: RTL-SDR Blog V3), mas a página de login/verificação impediu ler o preço. Banggood estava esgotado e não envia ao Brasil nesta consulta. Sem ele, o sintonizador FM do painel é só visual; o rádio online continua.
- **OBD melhor (OBDLink MX+ ou vLinker MC+)** — vale se o clone travar, for lento ou falhar no Mode 09 (VIN). Fichas no Mercado Livre sem preço confirmado.
- **Display oficial Raspberry Pi Touchscreen 7" v2 (DSI)** — [MakerHero](https://www.makerhero.com/produto/display-raspberry-pi-touchscreen-7/), R$ 759,90 na oferta, **fora de estoque**.
- **Módulo PC817 de 4 canais (UsinaInfo / MakerHero)** — fora de estoque; o Final usa 2× o módulo de 2 canais, que estava disponível.

## Como ler os totais

- **Kit Básico (Pix/à vista): R$ 2.548,90** (frete à parte).
- **Kit Final (Pix/à vista, já inclui o Básico com a troca da placa): R$ 3.920,57**.
- Preços mudam depressa, sobretudo Raspberry Pi (os reajustes de 2026 na linha 4/5 já aparecem no Brasil). Reabra a ficha antes de comprar.
- Ligue o Pi só depois do buck, no ACC, com fusível no 12 V. Veja a seção de ligação elétrica e desligamento seguro do [README](../README.md).
