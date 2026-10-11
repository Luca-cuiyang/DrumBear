/*
 * SPDX-License-Identifier: GPL-3.0-only
 * DB Score - 账户中心
 */
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import Muse.Ui
import Muse.UiComponents
import Muse.Dock
import Muse.Cloud

DockPage {
    id: root

    objectName: "Account"
    uri: "dbscore://account"

    property int sendCooldown: 0

    DbScoreAccountModel {
        id: accountModel
    }

    Timer {
        id: cooldownTimer
        interval: 1000
        repeat: true
        running: root.sendCooldown > 0
        onTriggered: {
            if (root.sendCooldown > 0) {
                root.sendCooldown -= 1
            }
        }
    }

    central: accountComp

    Component {
        id: accountComp

        Rectangle {
            anchors.fill: parent
            color: ui.theme.backgroundPrimaryColor

            Flickable {
                anchors.fill: parent
                contentWidth: width
                contentHeight: contentColumn.implicitHeight
                clip: true

                ColumnLayout {
                    id: contentColumn
                    width: parent.width
                    spacing: 16
                    anchors.margins: 28
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top

                    // 标题
                    StyledTextLabel {
                        text: qsTrc("appshell", "账户中心")
                        font: ui.theme.titleBoldFont
                    }

                    // 账号信息卡
                    Rectangle {
                        Layout.fillWidth: true
                        height: 92
                        radius: 12
                        color: ui.theme.backgroundSecondaryColor

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 18
                            spacing: 16

                            Rectangle {
                                width: 56
                                height: 56
                                radius: 28
                                color: ui.theme.accentColor

                                StyledTextLabel {
                                    anchors.centerIn: parent
                                    text: accountModel.phoneLoggedIn ? "🎵" : "👤"
                                    font: ui.theme.largeBodyFont
                                }
                            }

                            ColumnLayout {
                                spacing: 4

                                StyledTextLabel {
                                    text: accountModel.phoneLoggedIn
                                          ? (accountModel.phoneNickname.length > 0 ? accountModel.phoneNickname : accountModel.phoneMasked)
                                          : qsTrc("appshell", "未登录")
                                    font: ui.theme.largeBodyBoldFont
                                }

                                StyledTextLabel {
                                    text: accountModel.phoneLoggedIn
                                          ? accountModel.phoneMasked
                                          : qsTrc("appshell", "登录后开启会员与云服务")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }
                            }

                            Item { Layout.fillWidth: true }

                            FlatButton {
                                visible: accountModel.phoneLoggedIn
                                text: qsTrc("appshell", "退出登录")
                                onClicked: accountModel.logout()
                            }
                        }
                    }

                    // 会员状态卡
                    Rectangle {
                        Layout.fillWidth: true
                        height: 86
                        radius: 12
                        color: ui.theme.backgroundSecondaryColor

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 18
                            spacing: 16

                            ColumnLayout {
                                spacing: 6

                                StyledTextLabel {
                                    text: accountModel.hasProAccess ? qsTrc("appshell", "当前权益") : qsTrc("appshell", "会员状态")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }

                                StyledTextLabel {
                                    text: accountModel.statusText
                                    font: ui.theme.largeBodyFont
                                }
                            }

                            Item { Layout.fillWidth: true }

                            FlatButton {
                                visible: !accountModel.hasProAccess
                                text: qsTrc("appshell", "开通会员 ¥199/年")
                                accentButton: true
                                onClicked: accountModel.openPurchasePage()
                            }

                            FlatButton {
                                visible: accountModel.hasProAccess
                                text: qsTrc("appshell", "续费")
                                accentButton: true
                                onClicked: accountModel.openPurchasePage()
                            }
                        }
                    }

                    // 到期提醒
                    Rectangle {
                        visible: (accountModel.licenseState === 3 && accountModel.daysUntilExpiry <= 7)
                                 || accountModel.licenseState === 4
                        Layout.fillWidth: true
                        height: 58
                        radius: 12
                        color: ui.theme.accentColor
                        opacity: 0.9

                        StyledTextLabel {
                            anchors.centerIn: parent
                            text: accountModel.licenseState === 4
                                  ? qsTrc("appshell", "⚠️ 会员已过期，增值功能已锁定，请续费恢复。")
                                  : qsTrc("appshell", "🟠 会员将于 ") + accountModel.expireAtText
                                    + qsTrc("appshell", " 到期，请及时续费。")
                            font: ui.theme.bodyFont
                        }
                    }

                    // 手机号登录卡
                    Rectangle {
                        visible: !accountModel.phoneLoggedIn
                        Layout.fillWidth: true
                        height: 148
                        radius: 12
                        color: ui.theme.backgroundSecondaryColor

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 18
                            spacing: 12

                            StyledTextLabel {
                                text: qsTrc("appshell", "手机号登录")
                                font: ui.theme.largeBodyBoldFont
                            }

                            StyledTextLabel {
                                text: qsTrc("appshell", "注册即送3天免费试用，未注册手机号将自动注册")
                                font: ui.theme.bodyFont
                                opacity: 0.7
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                StyledTextLabel {
                                    text: qsTrc("appshell", "手机号")
                                    font: ui.theme.bodyFont
                                }

                                TextField {
                                    id: phoneField
                                    Layout.preferredWidth: 180
                                    placeholderText: qsTrc("appshell", "请输入手机号")
                                    inputMethodHints: Qt.ImhDigitsOnly
                                }

                                StyledTextLabel {
                                    text: qsTrc("appshell", "验证码")
                                    font: ui.theme.bodyFont
                                }

                                TextField {
                                    id: codeField
                                    Layout.preferredWidth: 130
                                    placeholderText: qsTrc("appshell", "6位验证码")
                                    inputMethodHints: Qt.ImhDigitsOnly
                                }

                                FlatButton {
                                    text: root.sendCooldown > 0
                                          ? (root.sendCooldown + qsTrc("appshell", "s 后重发"))
                                          : qsTrc("appshell", "获取验证码")
                                    enabled: !accountModel.busy && root.sendCooldown === 0
                                    onClicked: {
                                        console.log("AccountPage: sendCode clicked, phone=" + phoneField.text)
                                        accountModel.sendCode(phoneField.text)
                                        root.sendCooldown = 60
                                    }
                                }

                                FlatButton {
                                    text: qsTrc("appshell", "登录 / 注册")
                                    accentButton: true
                                    enabled: !accountModel.busy
                                    onClicked: accountModel.loginByPhone(phoneField.text, codeField.text)
                                }
                            }

                            StyledTextLabel {
                                visible: accountModel.lastError.length > 0
                                Layout.fillWidth: true
                                text: accountModel.lastError
                                color: ui.theme.accentColor
                                font: ui.theme.bodyFont
                                wrapMode: Text.WordWrap
                            }

                            StyledTextLabel {
                                visible: accountModel.sendCodeMessage.length > 0
                                Layout.fillWidth: true
                                text: accountModel.sendCodeMessage
                                color: ui.theme.fontPrimaryColor
                                font: ui.theme.bodyFont
                                wrapMode: Text.WordWrap
                            }
                        }
                    }

                    // 会员权益
                    Rectangle {
                        Layout.fillWidth: true
                        height: 220
                        radius: 12
                        color: ui.theme.backgroundSecondaryColor

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 18
                            spacing: 8

                            StyledTextLabel {
                                text: qsTrc("appshell", "会员专属权益")
                                font: ui.theme.largeBodyBoldFont
                            }

                            StyledTextLabel { text: qsTrc("appshell", "✅ 导入音频并与曲谱AI对齐"); font: ui.theme.bodyFont }
                            StyledTextLabel { text: qsTrc("appshell", "✅ 生成并导出动态.dbscore工程文件"); font: ui.theme.bodyFont }
                            StyledTextLabel { text: qsTrc("appshell", "✅ 批量导出MP4视频（1080P/2K/4K）"); font: ui.theme.bodyFont }
                            StyledTextLabel { text: qsTrc("appshell", "✅ 无水印输出文件"); font: ui.theme.bodyFont }
                            StyledTextLabel { text: qsTrc("appshell", "✅ 免费享受后续版本功能更新"); font: ui.theme.bodyFont }
                        }
                    }

                    // 激活码（备用入口）
                    Rectangle {
                        Layout.fillWidth: true
                        height: 76
                        radius: 12
                        color: ui.theme.backgroundSecondaryColor

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 18
                            spacing: 10

                            StyledTextLabel {
                                text: qsTrc("appshell", "激活码")
                                font: ui.theme.bodyFont
                            }

                            TextField {
                                id: licenseCodeField
                                Layout.fillWidth: true
                                placeholderText: qsTrc("appshell", "线下购买的用户在此输入激活码")
                            }

                            FlatButton {
                                text: qsTrc("appshell", "激活")
                                accentButton: true
                                enabled: !accountModel.busy
                                onClicked: accountModel.activate(licenseCodeField.text)
                            }
                        }
                    }

                    // 底部操作
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 12

                        FlatButton {
                            text: qsTrc("appshell", "刷新授权")
                            onClicked: accountModel.refresh()
                        }

                        Item { Layout.fillWidth: true }

                        StyledTextLabel {
                            text: qsTrc("appshell", "DB-Score年度会员 ¥199 / 年")
                            font: ui.theme.bodyFont
                            opacity: 0.6
                        }
                    }
                }
            }
        }
    }
}
