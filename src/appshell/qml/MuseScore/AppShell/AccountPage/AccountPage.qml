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

DockPage {
    id: root

    objectName: "Account"
    uri: "dbscore://account"

    property int previewStatus: 0
    property bool loggedIn: true

    function statusText() {
        switch (previewStatus) {
        case 0: return "✅正在3天免费试用期，剩余：X天X小时"
        case 1: return "🟡您的免费试用仅剩不到6小时，欢迎开通正式会员！"
        case 2: return "🟢DB-Score年度会员，到期时间：2027-10-11"
        case 3: return "🟠您的会员即将于 XXXX-XX-XX 到期，请及时续费，避免功能锁定！"
        case 4: return "⚠️会员已过期，请续费解锁增值功能"
        }
        return ""
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

                    StyledTextLabel {
                        text: qsTrc("appshell", "预览会员状态：")
                        font: ui.theme.bodyFont
                    }

                    FlatButton {
                        text: qsTrc("appshell", "试用中")
                        accentButton: root.previewStatus === 0
                        onClicked: root.previewStatus = 0
                    }
                    FlatButton {
                        text: qsTrc("appshell", "试用将到期")
                        accentButton: root.previewStatus === 1
                        onClicked: root.previewStatus = 1
                    }
                    FlatButton {
                        text: qsTrc("appshell", "正式会员")
                        accentButton: root.previewStatus === 2
                        onClicked: root.previewStatus = 2
                    }
                    FlatButton {
                        text: qsTrc("appshell", "即将到期")
                        accentButton: root.previewStatus === 3
                        onClicked: root.previewStatus = 3
                    }
                    FlatButton {
                        text: qsTrc("appshell", "已过期")
                        accentButton: root.previewStatus === 4
                        onClicked: root.previewStatus = 4
                    }

                    FlatButton {
                        text: root.loggedIn ? qsTrc("appshell", "已登录") : qsTrc("appshell", "未登录")
                        onClicked: root.loggedIn = !root.loggedIn
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
                                        text: root.loggedIn ? "微信昵称" : qsTrc("appshell", "未登录")
                                        font: ui.theme.largeBodyBoldFont
                                    }

                                    StyledTextLabel {
                                        text: root.loggedIn ? "138****0000" : qsTrc("appshell", "点击右侧登录按钮登录")
                                        font: ui.theme.bodyFont
                                    }
                                }

                                Item {
                                    Layout.fillWidth: true
                                }

                                FlatButton {
                                    visible: !root.loggedIn
                                    text: qsTrc("appshell", "登录")
                                    accentButton: true
                                    onClicked: loginDialog.open()
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
                                text: root.statusText()
                                font: ui.theme.largeBodyFont
                            }
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
                                onClicked: refreshToast.open()
                            }

                            FlatButton {
                                text: qsTrc("appshell", "去续费")
                                accentButton: true
                                onClicked: renewToast.open()
                            }

                            FlatButton {
                                text: qsTrc("appshell", "退出登录")
                                onClicked: logoutToast.open()
                            }
                        }

                        // 预览四款提醒弹窗
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            StyledTextLabel {
                                text: qsTrc("appshell", "提醒弹窗预览：")
                                font: ui.theme.bodyFont
                            }

                            FlatButton { text: qsTrc("appshell", "到期前7天"); onClicked: expireSoonDialog.open() }
                            FlatButton { text: qsTrc("appshell", "会员已过期"); onClicked: expiredDialog.open() }
                            FlatButton { text: qsTrc("appshell", "试用将到期"); onClicked: trialSoonDialog.open() }
                            FlatButton { text: qsTrc("appshell", "试用已结束"); onClicked: trialEndDialog.open() }
                        }

                        StyledTextLabel {
                            text: qsTrc("appshell", "DB-Score年度会员，定价：¥199 / 年。")
                            font: ui.theme.bodyFont
                            opacity: 0.6
                        }
                    }
                }
            }

            StyledDialogView {
                id: loginDialog
                width: 360
                height: 460

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    StyledTextLabel {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTrc("appshell", "登录")
                        font: ui.theme.titleBoldFont
                    }

                    StyledTextLabel {
                        text: qsTrc("appshell", "👉登录即可开启3天免费全功能试用！")
                        font: ui.theme.bodyFont
                        horizontalAlignment: Text.AlignHCenter
                    }

                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        width: 160
                        height: 160
                        radius: 10
                        color: ui.theme.backgroundSecondaryColor

                        StyledTextLabel {
                            anchors.centerIn: parent
                            text: "QR"
                            font: ui.theme.largeBodyFont
                        }
                    }

                    StyledTextLabel {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTrc("appshell", "微信扫码登录")
                        font: ui.theme.bodyFont
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        height: 1
                        color: ui.theme.strokeColor
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        StyledTextLabel { text: qsTrc("appshell", "手机号") }
                        TextField {
                            Layout.fillWidth: true
                            placeholderText: qsTrc("appshell", "请输入手机号")
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        StyledTextLabel { text: qsTrc("appshell", "验证码") }
                        TextField {
                            Layout.fillWidth: true
                            placeholderText: qsTrc("appshell", "请输入验证码")
                        }
                        FlatButton {
                            text: qsTrc("appshell", "获取验证码")
                        }
                    }

                    FlatButton {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTrc("appshell", "关闭")
                        onClicked: loginDialog.close()
                    }
                }
            }

            StyledDialogView {
                id: refreshToast
                width: 360
                height: 160
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTrc("appshell", "正在向服务器刷新授权（后端待接入）")
                        wrapMode: Text.WordWrap
                    }

                    FlatButton {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTrc("appshell", "确定")
                        onClicked: refreshToast.close()
                    }
                }
            }

            StyledDialogView {
                id: renewToast
                width: 380
                height: 160
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTrc("appshell", "即将跳转至drumbearai.com会员购买页面（后端待接入）")
                        wrapMode: Text.WordWrap
                    }

                    FlatButton {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTrc("appshell", "确定")
                        onClicked: renewToast.close()
                    }
                }
            }

            StyledDialogView {
                id: logoutToast
                width: 320
                height: 160
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTrc("appshell", "执行退出登录（后端待接入）")
                        wrapMode: Text.WordWrap
                    }

                    FlatButton {
                        Layout.alignment: Qt.AlignHCenter
                        text: qsTrc("appshell", "确定")
                        onClicked: logoutToast.close()
                    }
                }
            }

            StyledDialogView {
                id: expireSoonDialog
                width: 460
                height: 240
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    StyledTextLabel {
                        text: qsTrc("appshell", "🔔会员即将到期提醒")
                        font: ui.theme.titleBoldFont
                    }

                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTrc("appshell", "您好！您的DB-Score年度会员距离到期还有 X 天。\n为了不影响您正常使用音频对齐、导出动态工程、无水印导出视频等增值功能，请尽快续费。")
                        wrapMode: Text.WordWrap
                    }

                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 12

                        FlatButton { text: qsTrc("appshell", "去续费"); accentButton: true; onClicked: expireSoonDialog.close() }
                        FlatButton { text: qsTrc("appshell", "稍后提醒"); onClicked: expireSoonDialog.close() }
                    }
                }
            }

            StyledDialogView {
                id: expiredDialog
                width: 460
                height: 240
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    StyledTextLabel {
                        text: qsTrc("appshell", "❗会员已过期")
                        font: ui.theme.titleBoldFont
                    }

                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTrc("appshell", "您的DB-Score会员服务已经过期。\n基础乐谱编辑功能可以正常使用，但是音频对齐、导出动态工程、MP4导出等增值功能已锁定。")
                        wrapMode: Text.WordWrap
                    }

                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 12

                        FlatButton { text: qsTrc("appshell", "立即续费"); accentButton: true; onClicked: expiredDialog.close() }
                        FlatButton { text: qsTrc("appshell", "关闭"); onClicked: expiredDialog.close() }
                    }
                }
            }

            StyledDialogView {
                id: trialSoonDialog
                width: 460
                height: 250
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    StyledTextLabel {
                        text: qsTrc("appshell", "⏳免费试用即将到期")
                        font: ui.theme.titleBoldFont
                    }

                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTrc("appshell", "您好！您的DB-Score三天免费试用仅剩不到6小时。\n试用结束后，基础乐谱编辑仍然可用，音频对齐、导出动态工程、MP4导出等增值功能将会锁定。\n欢迎开通正式会员，持续享受全部高级能力！")
                        wrapMode: Text.WordWrap
                    }

                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 12

                        FlatButton { text: qsTrc("appshell", "立即开通会员"); accentButton: true; onClicked: trialSoonDialog.close() }
                        FlatButton { text: qsTrc("appshell", "稍后再说"); onClicked: trialSoonDialog.close() }
                    }
                }
            }

            StyledDialogView {
                id: trialEndDialog
                width: 470
                height: 260
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    StyledTextLabel {
                        text: qsTrc("appshell", "📢免费试用期已结束")
                        font: ui.theme.titleBoldFont
                    }

                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTrc("appshell", "您的3天免费试用已经结束。\n基础乐谱编辑、排版、PDF打印功能可永久免费使用；\n音频对齐、动态工程导出、MP4视频导出等增值功能已暂时锁定。\n如需继续使用高级功能，请开通年度会员。")
                        wrapMode: Text.WordWrap
                    }

                    RowLayout {
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 12

                        FlatButton { text: qsTrc("appshell", "去开通会员"); accentButton: true; onClicked: trialEndDialog.close() }
                        FlatButton { text: qsTrc("appshell", "关闭"); onClicked: trialEndDialog.close() }
                    }
                }
            }
        }
    }
}
