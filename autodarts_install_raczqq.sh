#!/bin/bash
sudo apt update
sudo apt install curl -y
#GITHUB_TOKEN="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"
SERVICE_PATH="/etc/systemd/system/led_ir.service"
SERVICE_IR_PATH="/etc/systemd/system/set-ir-protocol.service"
CONFIG_FILE="/boot/firmware/config.txt"
LINE="dtoverlay=gpio-ir,gpio_pin=17"
USER=$(whoami)
# Dodaj tylko, jeśli nie istnieje
if [ -f "$CONFIG_FILE" ]; then
	if ! grep -q "^$LINE" "$CONFIG_FILE"; then
		echo "$LINE" | sudo tee -a "$CONFIG_FILE"
		echo "Dodano: $LINE"
	else
		echo "Wpis już istnieje: $LINE"
 fi
else
  echo "Plik $CONFIG_FILE nie istnieje — pomijam wpis..."
fi
#ZMIENNA: adres URL pliku z GitHub
GITHUB_URL="https://raw.githubusercontent.com/QraczQQ/Autodarts_raczqq/refs/heads/main/led_ir.py"
# Ścieżka docelowa
DESTINATION="/home/$USER/$(basename "$GITHUB_URL")"
#Pobierz plik
echo "Pobieranie z: $GITHUB_URL"
#curl -H "Authorization: token $GITHUB_TOKEN"
curl -L "$GITHUB_URL" -o $DESTINATION
#Nadaj prawa do uruchomienia
chmod +x "$DESTINATION"
echo "Plik zapisano jako: $DESTINATION"
echo "Pobieram Autodarts..."
bash <(curl -sL get.autodarts.io)
echo "Tworzenie pliku systemd: $SERVICE_PATH"
sudo bash -c "cat > $SERVICE_PATH" << 'EOF'
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

 "Gotowe! Możesz teraz delektować się grą ! "
echo "Nastąpi restart urządzenia................"

for i in $(seq 5 -1 1); do
  echo -ne "Restart za $i sek...\r"
  sleep 1
done

echo -e "\nRebootuję teraz..."
sudo reboot



