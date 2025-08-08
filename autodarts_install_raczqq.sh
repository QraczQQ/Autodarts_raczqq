#!/bin/bash

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color (resetowanie koloru)

sudo apt update
sudo apt install curl -y
sudo apt install python3-rpi.gpio -y
sudo apt install lirc -y
sudo apt install ir-keytable -y
sudo pip3 install rpi_ws281x evdev -y
sudo git clone https://github.com/lbormann/darts-caller.git -y
sudo pip3 install -r requirements.txt--break-system-packages -y


SERVICE_PATH="/etc/systemd/system/led_ir.service"
SERVICE_IR_PATH="/etc/systemd/system/set-ir-protocol.service"
CONFIG_FILE="/boot/firmware/config.txt"
LINE="dtoverlay=gpio-ir,gpio_pin=17"
LINE2="dtoverlay=gpio-fan,gpiopin=14,temp=60000"
USER=$(logname)

sudo usermod -aG gpio $USER

# Dodaj tylko, jeśli nie istnieje
if [ -f "$CONFIG_FILE" ]; then
	if ! grep -q "^$LINE" "$CONFIG_FILE"; then
		echo "$LINE" | sudo tee -a "$CONFIG_FILE"
		echo -e "${GREEN}Dodano: $LINE ${NC}"
	else
		echo -e "${YELLOW}Wpis już istnieje: $LINE ${NC}"
  	
   if ! grep -q "^$LINE2" "$CONFIG_FILE"; then
		echo "$LINE2" | sudo tee -a "$CONFIG_FILE"
		echo -e "${GREEN}Dodano: $LINE2 ${NC}"
	else
		echo -e "${YELLOW}Wpis już istnieje: $LINE2 ${NC}"
 fi
else
  echo -e "${RED}Plik $CONFIG_FILE nie istnieje — pomijam wpis...${NC}"
fi
#ZMIENNA: adres URL pliku z GitHub
GITHUB_URL="https://raw.githubusercontent.com/QraczQQ/Autodarts_raczqq/refs/heads/main/led_ir.py"
# Ścieżka docelowa
DESTINATION="/home/$USER/$(basename "$GITHUB_URL")"
#Pobierz plik
echo -e "${YELLOW}Pobieranie z:${NC} $GITHUB_URL"
#curl -H "Authorization: token $GITHUB_TOKEN"
curl -L "$GITHUB_URL" -o $DESTINATION
#Nadaj prawa do uruchomienia
chmod +x "$DESTINATION"
echo -e "${GREEN}Plik zapisano jako:${NC} $DESTINATION"
echo -e "${BLUE}Pobieram Autodarts...${NC}"
bash <(curl -sL get.autodarts.io)
echo "Tworzenie pliku systemd: $SERVICE_PATH"
sudo bash -c "cat > $SERVICE_PATH" << EOF
[Unit]
Description=Monitor autodarts status and start LED IR
After=network.target autodarts.service
Requires=autodarts.service
[Service]
ExecStart=/usr/bin/python3 /home/$USER/led_ir.py
ExecStartPre=/bin/sleep 2
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
User=root
Environment=PYTHONUNBUFFERED=1
[Install]
WantedBy=multi-user.target
EOF
echo "Tworzenie pliku systemd: $SERVICE_IR_PATH"
sudo bash -c "cat > $SERVICE_IR_PATH" << 'EOF'
[Unit]
Description=Set IR protocol to NEC
After=multi-user.target
[Service]
ExecStart=/usr/bin/ir-keytable -p nec
Type=oneshot
[Install]
WantedBy=multi-user.target
EOF
echo "Ustawianie uprawnień..."
sudo chmod 644 $SERVICE_PATH
sudo chmod 644 $SERVICE_IR_PATH
echo "Przeładowywanie systemd..."
sudo systemctl daemon-reexec
echo "Włączanie usługi led_ir.service..."
sudo systemctl enable led_ir.service
sudo systemctl enable set-ir-protocol.service

sleep 2

sudo systemctl start set-ir-protocol.service
sudo systemctl start led_ir.service

echo -e "${GREEN}[OK]Gotowe! Możesz teraz delektować się grą ! ${NC}"
echo -e "${YELLOW}Nastąpi restart urządzenia................${NC}"

for i in $(seq 5 -1 1); do
  echo -ne "${YELLOW}Restart za $i sek...\r${NC}"
  sleep 1
done

echo -e "\nRebootuję teraz..."
sudo reboot



