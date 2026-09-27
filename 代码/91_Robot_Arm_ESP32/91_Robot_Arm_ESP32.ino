/* -------------------------------------------------
Copyright (c)
Arduino project by Tech Talkies YouTube Channel.
https://www.youtube.com/@techtalkies1
-------------------------------------------------*/

#include <WiFi.h>
#include <WiFiAP.h>
#include <WebServer.h>
#include <Preferences.h>
#include <ESP32Servo.h>
#include "web.h"

const char* ssid = "ESP32 Robot";
const char* password = "12345678";

WebServer server(80);

static const int servoPinLR = D2;
static const int servoPinFB = D3;
static const int servoPinUD = D4;
static const int servoPinGrip = D5;

Servo servoLR, servoFB, servoUD, servoGrip;
Preferences preferences;

const int GRIP_OPEN = 180;
const int GRIP_CLOSE = 60;

// Factory defaults. The web panel can save a calibrated HOME pose in flash.
// Keep the first test below 120 degrees and adjust one joint at a time.
const int DEFAULT_HOME_LR = 90;       // base: left / right
const int DEFAULT_HOME_FB = 90;       // shoulder: forward / backward
const int DEFAULT_HOME_UD = 90;       // elbow: up / down
const int DEFAULT_HOME_GRIP = GRIP_OPEN;

// Soft limits protect the printed links from being driven to their hard stops.
// Narrow these after checking the real assembly. They are logical angles shown in the UI.
const int LIMIT_LR_MIN = 10;
const int LIMIT_LR_MAX = 170;
const int LIMIT_FB_MIN = 10;
const int LIMIT_FB_MAX = 170;
const int LIMIT_UD_MIN = 10;
const int LIMIT_UD_MAX = 170;
const int LIMIT_GRIP_MIN = 55;
const int LIMIT_GRIP_MAX = 180;

int home_lr = DEFAULT_HOME_LR;
int home_fb = DEFAULT_HOME_FB;
int home_ud = DEFAULT_HOME_UD;
int home_grip = DEFAULT_HOME_GRIP;

int lr_target = DEFAULT_HOME_LR;
int fb_target = DEFAULT_HOME_FB;
int ud_target = DEFAULT_HOME_UD;
int grip_target = DEFAULT_HOME_GRIP;

int lr_current = DEFAULT_HOME_LR;
int fb_current = DEFAULT_HOME_FB;
int ud_current = DEFAULT_HOME_UD;
int grip_current = DEFAULT_HOME_GRIP;

const int STEP_ARM = 3;   // responsive but still progressive arm motion
const int STEP_GRIP = 6;  // gripper can move slightly faster
const unsigned long SERVO_UPDATE_MS = 15;

int clampAxis(const String& axis, int value) {
  if (axis == "lr") return constrain(value, LIMIT_LR_MIN, LIMIT_LR_MAX);
  if (axis == "fb") return constrain(value, LIMIT_FB_MIN, LIMIT_FB_MAX);
  if (axis == "ud") return constrain(value, LIMIT_UD_MIN, LIMIT_UD_MAX);
  return constrain(value, LIMIT_GRIP_MIN, LIMIT_GRIP_MAX);
}

void loadHomePose() {
  preferences.begin("robot-arm", true);
  home_lr = clampAxis("lr", preferences.getInt("home_lr", DEFAULT_HOME_LR));
  home_fb = clampAxis("fb", preferences.getInt("home_fb", DEFAULT_HOME_FB));
  home_ud = clampAxis("ud", preferences.getInt("home_ud", DEFAULT_HOME_UD));
  home_grip = clampAxis("grip", preferences.getInt("home_grip", DEFAULT_HOME_GRIP));
  preferences.end();

  lr_target = lr_current = home_lr;
  fb_target = fb_current = home_fb;
  ud_target = ud_current = home_ud;
  grip_target = grip_current = home_grip;
}

void saveHomePose() {
  home_lr = lr_target;
  home_fb = fb_target;
  home_ud = ud_target;
  home_grip = grip_target;

  preferences.begin("robot-arm", false);
  preferences.putInt("home_lr", home_lr);
  preferences.putInt("home_fb", home_fb);
  preferences.putInt("home_ud", home_ud);
  preferences.putInt("home_grip", home_grip);
  preferences.end();
}

String poseJson() {
  String response = "{\"current\":{\"lr\":" + String(lr_current) +
                    ",\"fb\":" + String(fb_current) +
                    ",\"ud\":" + String(ud_current) +
                    ",\"grip\":" + String(grip_current) +
                    "},\"target\":{\"lr\":" + String(lr_target) +
                    ",\"fb\":" + String(fb_target) +
                    ",\"ud\":" + String(ud_target) +
                    ",\"grip\":" + String(grip_target) +
                    "},\"home\":{\"lr\":" + String(home_lr) +
                    ",\"fb\":" + String(home_fb) +
                    ",\"ud\":" + String(home_ud) +
                    ",\"grip\":" + String(home_grip) +
                    "},\"ip\":\"" + WiFi.softAPIP().toString() +
                    "\",\"uptime\":" + String(millis() / 1000) + "}";
  return response;
}

void handleStatus() {
  server.send(200, "application/json", poseJson());
}

void handleHome() {
  lr_target = home_lr;
  fb_target = home_fb;
  ud_target = home_ud;
  grip_target = home_grip;
  server.send(200, "application/json", poseJson());
}

void handleSaveHome() {
  saveHomePose();
  server.send(200, "application/json", poseJson());
}

void handleHomeConfig() {
  if (!server.hasArg("lr") || !server.hasArg("fb") ||
      !server.hasArg("ud") || !server.hasArg("grip")) {
    server.send(400, "application/json", "{\"ok\":false,\"message\":\"Missing angle\"}");
    return;
  }

  lr_target = clampAxis("lr", server.arg("lr").toInt());
  fb_target = clampAxis("fb", server.arg("fb").toInt());
  ud_target = clampAxis("ud", server.arg("ud").toInt());
  grip_target = clampAxis("grip", server.arg("grip").toInt());

  if (server.arg("save") == "1") {
    saveHomePose();
  }

  server.send(200, "application/json", poseJson());
}

void handleFactoryHome() {
  home_lr = clampAxis("lr", DEFAULT_HOME_LR);
  home_fb = clampAxis("fb", DEFAULT_HOME_FB);
  home_ud = clampAxis("ud", DEFAULT_HOME_UD);
  home_grip = clampAxis("grip", DEFAULT_HOME_GRIP);
  preferences.begin("robot-arm", false);
  preferences.putInt("home_lr", home_lr);
  preferences.putInt("home_fb", home_fb);
  preferences.putInt("home_ud", home_ud);
  preferences.putInt("home_grip", home_grip);
  preferences.end();
  handleHome();
}

void handleJog() {
  String axis = server.arg("axis");
  int delta = constrain(server.arg("delta").toInt(), -20, 20);
  if (axis == "lr") lr_target = clampAxis(axis, lr_target + delta);
  else if (axis == "fb") fb_target = clampAxis(axis, fb_target + delta);
  else if (axis == "ud") ud_target = clampAxis(axis, ud_target + delta);
  else if (axis == "grip") grip_target = clampAxis(axis, grip_target + delta);
  server.send(200, "application/json", poseJson());
}

void handleServo() {

  if (server.hasArg("lr"))
    lr_target = clampAxis("lr", server.arg("lr").toInt());

  if (server.hasArg("fb"))
    fb_target = clampAxis("fb", server.arg("fb").toInt());

  if (server.hasArg("ud"))
    ud_target = clampAxis("ud", server.arg("ud").toInt());

  if (server.hasArg("grip")) {
    int g = server.arg("grip").toInt();
    // Accept both the old 0/1 button protocol and the new angle slider.
    grip_target = (g == 1) ? GRIP_CLOSE : ((g == 0) ? GRIP_OPEN : clampAxis("grip", g));
  }

  Serial.printf("T -> lr:%d fb:%d ud:%d grip:%d\n",
                lr_target, fb_target, ud_target, grip_target);

  // Quick ACK
  server.send(200, "text/plain", "ok");
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_AP);
  WiFi.softAP(ssid, password);
  delay(1000);
  IPAddress IP = IPAddress(10, 10, 10, 1);
  IPAddress NMask = IPAddress(255, 255, 255, 0);
  WiFi.softAPConfig(IP, IP, NMask);
  IPAddress myIP = WiFi.softAPIP();
  Serial.print("AP IP address: ");
  Serial.println(myIP);

  /* SETUP YOR WEB OWN ENTRY POINTS */
  server.on("/servo", handleServo);
  server.on("/home", HTTP_GET, handleHome);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/home/save", HTTP_GET, handleSaveHome);
  server.on("/home/config", HTTP_POST, handleHomeConfig);
  server.on("/home/factory", HTTP_GET, handleFactoryHome);
  server.on("/jog", HTTP_GET, handleJog);

  // Route for root / web page
  server.on("/", HTTP_GET, []() {
    server.send_P(200, "text/html", index_html);
  });

  server.begin();
  Serial.println("HTTP server started");

  loadHomePose();

  servoLR.attach(servoPinLR);
  servoFB.attach(servoPinFB);
  servoUD.attach(servoPinUD);
  servoGrip.attach(servoPinGrip);

  // Write a known safe startup pose immediately after attaching the servos.
  servoLR.write(home_lr);
  servoFB.write(home_fb);
  servoUD.write(home_ud);
  servoGrip.write(home_grip);
}

void loop() {
  server.handleClient();
  delay(2);  //allow the cpu to switch to other tasks

  static unsigned long lastUpdate = 0;
  if (millis() - lastUpdate >= SERVO_UPDATE_MS) {
    lastUpdate = millis();

    // Left / Right
    if (lr_current < lr_target) lr_current += STEP_ARM;
    else if (lr_current > lr_target) lr_current -= STEP_ARM;
    if (abs(lr_current - lr_target) < STEP_ARM) lr_current = lr_target;

    // Forward / Backward
    if (fb_current < fb_target) fb_current += STEP_ARM;
    else if (fb_current > fb_target) fb_current -= STEP_ARM;
    if (abs(fb_current - fb_target) < STEP_ARM) fb_current = fb_target;

    // Up / Down
    if (ud_current < ud_target) ud_current += STEP_ARM;
    else if (ud_current > ud_target) ud_current -= STEP_ARM;
    if (abs(ud_current - ud_target) < STEP_ARM) ud_current = ud_target;

    // Gripper (faster, or even snap if you want)
    if (grip_current < grip_target) grip_current += STEP_GRIP;
    else if (grip_current > grip_target) grip_current -= STEP_GRIP;
    if (abs(grip_current - grip_target) < STEP_GRIP) grip_current = grip_target;

    // ---- ACTUAL SERVO OUTPUTS HERE ----
    servoLR.write(lr_current);
    servoFB.write(fb_current);
    servoUD.write(ud_current);
    servoGrip.write(grip_current);
  }
}
