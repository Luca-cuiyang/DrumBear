/*
 * SPDX-License-Identifier: GPL-3.0-only
 * DB Score - Account Center (static UI only, no backend)
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

    DbScoreAccountModel {
        id: accountModel
    }

    central: accountComp

    Component {
        id: accountComp

        Rectangle {
            anchors.fill: parent
            color: ui.theme.backgroundPrimaryColor

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 24
                spacing: 16

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTrc("appshell", "账户中心")
                        font: ui.theme.titleBoldFont
                        horizontalAlignment: Text.AlignLeft
                    }
                }

                Flickable {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentWidth: width
                    contentHeight: contentColumn.implicitHeight
                    clip: true

                    ColumnLayout {
                        id: contentColumn
                        width: parent.width
                        spacing: 16

                        // 头部账号信息区
                        Rectangle {
                            Layout.fillWidth: true
                            height: 96
                            radius: 10
                            color: ui.theme.backgroundSecondaryColor

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 16
                                spacing: 16

                                Rectangle {
                                    width: 64
                                    height: 64
                                    radius: 32
                                    color: ui.theme.accentColor

                                    StyledTextLabel {
                                        anchors.centerIn: parent
                                        text: "👤"
                                        font: ui.theme.largeBodyFont
                                    }
                                }

                                ColumnLayout {
                                    spacing: 6

                                    StyledTextLabel {
                                        text: accountModel.memberType === "standard"
                                              ? qsTrc("appshell", "正式会员")
                                              : (accountModel.hasProAccess ? qsTrc("appshell", "免费试用中") : qsTrc("appshell", "未激活"))
                                        font: ui.theme.largeBodyBoldFont
                                    }

                                    StyledTextLabel {
                                        text: qsTrc("appshell", "设备标识：") + accountModel.deviceId
                                        font: ui.theme.bodyFont
                                        elide: Text.ElideMiddle
                                    }
                                }

                                Item {
                                    Layout.fillWidth: true
                                }

                                FlatButton {
                                    text: qsTrc("appshell", "去续费")
                                    accentButton: true
                                    onClicked: accountModel.openPurchasePage()
                                }
                            }
                        }

                        // 会员状态展示区
                        Rectangle {
                            Layout.fillWidth: true
                            height: 72
                            radius: 10
                            color: ui.theme.backgroundSecondaryColor

                            StyledTextLabel {
                                anchors.centerIn: parent
                                text: accountModel.statusText
                                font: ui.theme.largeBodyFont
                            }
                        }

                        // 到期提醒（licenseState: 3=Active 正式会员, 4=Expired 已过期）
                        Rectangle {
                            visible: (accountModel.licenseState === 3 && accountModel.daysUntilExpiry <= 7)
                                     || accountModel.licenseState === 4
                            Layout.fillWidth: true
                            height: 64
                            radius: 10
                            color: ui.theme.accentColor
                            opacity: 0.9

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 10

                                StyledTextLabel {
                                    Layout.fillWidth: true
                                    text: accountModel.licenseState === 4
                                          ? qsTrc("appshell", "⚠️会员已过期，增值功能已锁定，请续费恢复使用。")
                                          : qsTrc("appshell", "🟠会员即将于 ") + accountModel.expireAtText
                                            + qsTrc("appshell", " 到期，请及时续费。")
                                    font: ui.theme.bodyFont
                                    wrapMode: Text.WordWrap
                                }

                                FlatButton {
                                    text: qsTrc("appshell", "去续费")
                                    onClicked: accountModel.openPurchasePage()
                                }
                            }
                        }

                        // 激活码输入区
                        Rectangle {
                            Layout.fillWidth: true
                            height: 72
                            radius: 10
                            color: ui.theme.backgroundSecondaryColor

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 10

                                StyledTextLabel {
                                    text: qsTrc("appshell", "激活码")
                                    font: ui.theme.bodyFont
                                }

                                TextField {
                                    id: licenseCodeField
                                    Layout.fillWidth: true
                                    placeholderText: qsTrc("appshell", "请输入激活码")
                                }

                                FlatButton {
                                    text: qsTrc("appshell", "激活")
                                    accentButton: true
                                    enabled: !accountModel.busy
                                    onClicked: accountModel.activate(licenseCodeField.text)
                                }

                                FlatButton {
                                    text: qsTrc("appshell", "刷新授权")
                                    enabled: !accountModel.busy
                                    onClicked: accountModel.refresh()
                                }
                            }
                        }

                        // 错误提示
                        StyledTextLabel {
                            visible: accountModel.lastError.length > 0
                            Layout.fillWidth: true
                            text: accountModel.lastError
                            color: ui.theme.accentColor
                            font: ui.theme.bodyFont
                            wrapMode: Text.WordWrap
                        }

                        // 授权信息
                        StyledTextLabel {
                            Layout.fillWidth: true
                            text: qsTrc("appshell", "设备标识：") + accountModel.deviceId
                            font: ui.theme.bodyFont
                            opacity: 0.6
                        }

                        // 会员专属权益
                        Rectangle {
                            Layout.fillWidth: true
                            height: 220
                            radius: 10
                            color: ui.theme.backgroundSecondaryColor

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 16
                                spacing: 8

                                StyledTextLabel {
                                    text: qsTrc("appshell", "会员专属权益")
                                    font: ui.theme.largeBodyBoldFont
                                }

                                StyledTextLabel { text: qsTrc("appshell", "✅导入音频并与曲谱AI对齐"); font: ui.theme.bodyFont }
                                StyledTextLabel { text: qsTrc("appshell", "✅生成并导出动态.dbscore工程文件"); font: ui.theme.bodyFont }
                                StyledTextLabel { text: qsTrc("appshell", "✅批量导出MP4视频（1080P/2K/4K多种分辨率）"); font: ui.theme.bodyFont }
                                StyledTextLabel { text: qsTrc("appshell", "✅无水印输出文件"); font: ui.theme.bodyFont }
                                StyledTextLabel { text: qsTrc("appshell", "✅免费享受后续版本功能更新"); font: ui.theme.bodyFont }
                            }
                        }

                        // 操作按钮组
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            FlatButton {
                                text: qsTrc("appshell", "刷新授权")
                                onClicked: accountModel.refresh()
                            }

                            FlatButton {
                                text: qsTrc("appshell", "去续费")
                                accentButton: true
                                onClicked: accountModel.openPurchasePage()
                            }

                            FlatButton {
                                text: qsTrc("appshell", "清除授权")
                                onClicked: accountModel.clearLicense()
                            }
                        }

                        StyledTextLabel {
                            text: qsTrc("appshell", "DB-Score年度会员，定价：¥199 / 年。")
                            font: ui.theme.bodyFont
                            opacity: 0.6
                        }
                    }
                }
            }

            // 提醒弹窗将在后续版本按会员状态自动触发
        }
    }
}
