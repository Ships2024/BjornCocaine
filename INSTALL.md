## 🔧 Установка и настройка

<p align="center">
  <img src="https://github.com/user-attachments/assets/c5eb4cc1-0c3d-497d-9422-1614651a84ab" alt="thumbnail_IMG_0546" width="98">
</p>

## 📚 Содержание

- [Предварительные требования](#-предварительные-требования)
- [Быстрая установка](#-быстрая-установка)
- [Ручная установка](#-ручная-установка)
- [Лицензия](#-лицензия)

Используйте Raspberry Pi Imager для установки вашей ОС
https://www.raspberrypi.com/software/

### 📌 Предварительные требования для RPI zero W (32-бит)
![image](https://github.com/user-attachments/assets/3980ec5f-a8fc-4848-ab25-4356e0529639)

- Установлена Raspberry Pi OS. 
    - Стабильная:
      - Система: 32-битная
      - Версия ядра: 6.6
      - Версия Debian: 12 (bookworm) '2024-10-22-raspios-bookworm-armhf-lite'
- Имя пользователя и имя хоста установлены на `bjorn`.
- 2,13-дюймовый e-Paper HAT подключен к выводам GPIO.

### 📌 Предварительные требования для RPI zero W2 (64-бит)

![image](https://github.com/user-attachments/assets/e8d276be-4cb2-474d-a74d-b5b6704d22f5)

Я не разрабатывал Bjorn для raspberry pi zero w2 64-бит, но несколько отзывов подтвердили, что установка прошла успешно.

- Установлена Raspberry Pi OS. 
    - Стабильная:
      - Система: 64-битная
      - Версия ядра: 6.6
      - Версия Debian: 12 (bookworm) '2024-10-22-raspios-bookworm-arm64-lite'
- Имя пользователя и имя хоста установлены на `bjorn`.
- 2,13-дюймовый e-Paper HAT подключен к выводам GPIO.



На данный момент протестированы и реализованы экраны e-Paper v2 и v4.
Я просто надеюсь, что V1 и V3 будут работать так же.
 
### ⚡ Быстрая установка

Самый быстрый способ установить Bjorn — использовать скрипт автоматической установки:

```bash
# Загрузить и запустить установщик
wget https://raw.githubusercontent.com/infinition/Bjorn/refs/heads/main/install_bjorn.sh
sudo chmod +x install_bjorn.sh
sudo ./install_bjorn.sh
# Выберите вариант 1 для автоматической установки. Это может занять некоторое время, так как будет установлено много пакетов и модулей. В конце необходимо перезагрузиться.
```

### 🧰 Ручная установка

#### Шаг 1: Активируйте SPI и I2C

```bash
sudo raspi-config
```

- Перейдите к **"Interface Options"**.
- Включите **SPI**.
- Включите **I2C**.

#### Шаг 2: Системные зависимости

```bash
# Обновить систему
sudo apt-get update && sudo apt-get upgrade -y

# Установить необходимые пакеты

 sudo apt install -y \
  libjpeg-dev \
  zlib1g-dev \
  libpng-dev \
  python3-dev \
  libffi-dev \
  libssl-dev \
  libgpiod-dev \
  libi2c-dev \
  libatlas-base-dev \
  build-essential \
  python3-pip \
  wget \
  lsof \
  git \
  libopenjp2-7 \
  nmap \
  libopenblas-dev \
  bluez-tools \
  bluez \
  dhcpcd5 \
  bridge-utils \
  python3-pil


# Обновить базу данных скриптов Nmap

sudo nmap --script-updatedb

```

#### Шаг 3: Установка Bjorn

```bash
# Клонировать репозиторий Bjorn
cd /home/bjorn
git clone https://github.com/infinition/Bjorn.git
cd Bjorn

# Установить зависимости Python в виртуальном окружении
sudo pip install -r requirements.txt --break-system-packages
# Поскольку мне "пока" не удалось добиться стабильной установки с виртуальным окружением, я установил зависимости в масштабе всей системы (с --break-system-packages), до сих пор это не вызывало никаких проблем. Вы можете попробовать установить их в виртуальном окружении, если хотите.
```

##### 3.1: Настройте тип дисплея E-Paper
Выберите версию вашего e-Paper HAT, изменив файл конфигурации:

1. Откройте файл конфигурации:
```bash
sudo vi /home/bjorn/Bjorn/config/shared_config.json
```
Нажмите i, чтобы войти в режим вставки
Найдите строку, содержащую "epd_type":
Измените значение в соответствии с моделью вашего экрана:

- Для 2.13 V1: "epd_type": "epd2in13",
- Для 2.13 V2: "epd_type": "epd2in13_V2",
- Для 2.13 V3: "epd_type": "epd2in13_V3",
- Для 2.13 V4: "epd_type": "epd2in13_V4",

Нажмите Esc, чтобы выйти из режима вставки
Введите :wq и нажмите Enter, чтобы сохранить и выйти

#### Шаг 4: Настройте ограничения файловых дескрипторов

Чтобы предотвратить ошибку `OSError: [Errno 24] Too many open files`, необходимо увеличить ограничения файловых дескрипторов.

##### 4.1: Измените ограничения файловых дескрипторов для всех пользователей

Отредактируйте `/etc/security/limits.conf`:

```bash
sudo vi /etc/security/limits.conf
```

Добавьте следующие строки:

```
* soft nofile 65535
* hard nofile 65535
root soft nofile 65535
root hard nofile 65535
```

##### 4.2: Настройте ограничения Systemd

Отредактируйте `/etc/systemd/system.conf`:

```bash
sudo vi /etc/systemd/system.conf
```

Раскомментируйте и измените:

```
DefaultLimitNOFILE=65535
```

Отредактируйте `/etc/systemd/user.conf`:

```bash
sudo vi /etc/systemd/user.conf
```

Раскомментируйте и измените:

```
DefaultLimitNOFILE=65535
```

##### 4.3: Создайте или измените `/etc/security/limits.d/90-nofile.conf`

```bash
sudo vi /etc/security/limits.d/90-nofile.conf
```

Добавьте:

```
root soft nofile 65535
root hard nofile 65535
```

##### 4.4: Настройте общесистемное ограничение файловых дескрипторов

Отредактируйте `/etc/sysctl.conf`:

```bash
sudo vi /etc/sysctl.conf
```

Добавьте:

```
fs.file-max = 2097152
```

Примените изменения:

```bash
sudo sysctl -p
```

#### Шаг 5: Перезагрузите Systemd и примените изменения

Перезагрузите systemd, чтобы применить новые ограничения файловых дескрипторов:

```bash
sudo systemctl daemon-reload
```

#### Шаг 6: Измените файлы конфигурации PAM

PAM (Pluggable Authentication Modules) управляет тем, как применяются ограничения для пользовательских сеансов. Чтобы обеспечить соблюдение новых ограничений файловых дескрипторов, обновите следующие файлы конфигурации.

##### Шаг 6.1: Отредактируйте `/etc/pam.d/common-session` и `/etc/pam.d/common-session-noninteractive`

```bash
sudo vi /etc/pam.d/common-session
sudo vi /etc/pam.d/common-session-noninteractive
```

Добавьте эту строку в конец обоих файлов:

```
session required pam_limits.so
```

Это гарантирует, что ограничения, установленные в `/etc/security/limits.conf`, будут применяться для всех пользовательских сеансов.

#### Шаг 7: Настройте службы

##### 7.1: Служба Bjorn

Создайте файл службы:

```bash
sudo vi /etc/systemd/system/bjorn.service
```

Добавьте следующее содержимое:

```ini
[Unit]
Description=Bjorn Service
DefaultDependencies=no
Before=basic.target
After=local-fs.target

[Service]
ExecStartPre=/home/bjorn/Bjorn/kill_port_8000.sh
ExecStart=/usr/bin/python3 /home/bjorn/Bjorn/Bjorn.py
WorkingDirectory=/home/bjorn/Bjorn
StandardOutput=inherit
StandardError=inherit
Restart=always
User=root

# Проверять открытые файлы и перезапускать, если достигнут лимит (буфер ulimit -n из 1000)
ExecStartPost=/bin/bash -c 'FILE_LIMIT=$(ulimit -n); THRESHOLD=$(( FILE_LIMIT - 1000 )); while :; do TOTAL_OPEN_FILES=$(lsof | wc -l); if [ "$TOTAL_OPEN_FILES" -ge "$THRESHOLD" ]; then echo "Достигнут порог файловых дескрипторов: $TOTAL_OPEN_FILES (порог: $THRESHOLD). Перезапуск службы."; systemctl restart bjorn.service; exit 0; fi; sleep 10; done &'

[Install]
WantedBy=multi-user.target
```



##### 7.2: Скрипт для освобождения порта 8000

Создайте скрипт для освобождения порта 8000:

```bash
vi /home/bjorn/Bjorn/kill_port_8000.sh
```

Добавьте:

```bash
#!/bin/bash
PORT=8000
PIDS=$(lsof -t -i:$PORT)

if [ -n "$PIDS" ]; then
    echo "Завершение процессов, использующих порт $PORT: $PIDS"
    kill -9 $PIDS
fi
```

Сделайте скрипт исполняемым:

```bash
chmod +x /home/bjorn/Bjorn/kill_port_8000.sh
```


##### 7.3: Конфигурация USB-гаджета

Измените `/boot/firmware/cmdline.txt`:

```bash
sudo vi /boot/firmware/cmdline.txt
```

Добавьте следующее сразу после `rootwait`:

```
modules-load=dwc2,g_ether
```

Измените `/boot/firmware/config.txt`:

```bash
sudo vi /boot/firmware/config.txt
```

Добавьте в конец файла:

```
dtoverlay=dwc2
```

Создайте скрипт USB-гаджета:

```bash
sudo vi /usr/local/bin/usb-gadget.sh
```

Добавьте следующее содержимое:

```bash
#!/bin/bash
set -e

modprobe libcomposite
cd /sys/kernel/config/usb_gadget/
mkdir -p g1
cd g1

echo 0x1d6b > idVendor
echo 0x0104 > idProduct
echo 0x0100 > bcdDevice
echo 0x0200 > bcdUSB

mkdir -p strings/0x409
echo "fedcba9876543210" > strings/0x409/serialnumber
echo "Raspberry Pi" > strings/0x409/manufacturer
echo "Pi Zero USB" > strings/0x409/product

mkdir -p configs/c.1/strings/0x409
echo "Config 1: ECM network" > configs/c.1/strings/0x409/configuration
echo 250 > configs/c.1/MaxPower

mkdir -p functions/ecm.usb0

# Проверить наличие существующей символической ссылки и удалить при необходимости
if [ -L configs/c.1/ecm.usb0 ]; then
    rm configs/c.1/ecm.usb0
fi
ln -s functions/ecm.usb0 configs/c.1/

# Убедиться, что устройство не занято, прежде чем перечислять доступные контроллеры USB-устройств
max_retries=10
retry_count=0

while ! ls /sys/class/udc > UDC 2>/dev/null; do
    if [ $retry_count -ge $max_retries ]; then
        echo "Ошибка: Устройство или ресурс заняты после $max_retries попыток."
        exit 1
    fi
    retry_count=$((retry_count + 1))
    sleep 1
done

# Проверить, настроен ли уже интерфейс usb0
if ! ip addr show usb0 | grep -q "172.20.2.1"; then
    ifconfig usb0 172.20.2.1 netmask 255.255.255.0
else
    echo "Интерфейс usb0 уже настроен."
fi
```

Сделайте скрипт исполняемым:

```bash
sudo chmod +x /usr/local/bin/usb-gadget.sh
```

Создайте службу systemd:

```bash
sudo vi /etc/systemd/system/usb-gadget.service
```

Добавьте:

```ini
[Unit]
Description=USB Gadget Service
After=network.target

[Service]
ExecStartPre=/sbin/modprobe libcomposite
ExecStart=/usr/local/bin/usb-gadget.sh
Type=simple
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

Настройте `usb0`:

```bash
sudo vi /etc/network/interfaces
```

Добавьте:

```bash
allow-hotplug usb0
iface usb0 inet static
    address 172.20.2.1
    netmask 255.255.255.0
```

Перезагрузите службы:

```bash
sudo systemctl daemon-reload
sudo systemctl enable systemd-networkd
sudo systemctl enable usb-gadget
sudo systemctl start systemd-networkd
sudo systemctl start usb-gadget
```

Необходимо перезагрузиться, чтобы использовать его как USB-гаджет (с IP-адресом).
###### Конфигурация ПК с Windows

Установите статический IP-адрес на вашем ПК с Windows:

- **IP-адрес**: `172.20.2.2`
- **Маска подсети**: `255.255.255.0`
- **Основной шлюз**: `172.20.2.1`
- **DNS-серверы**: `8.8.8.8`, `8.8.4.4`

---

## 📜 Лицензия

2024 - Bjorn распространяется по лицензии MIT. Для получения более подробной информации см. файл [LICENSE](LICENSE), включенный в этот репозиторий.
