/*
 * SPDX-License-Identifier: GPL-3.0-only
 * DB Score - 个人中心
 */
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import Muse.Ui
import Muse.UiComponents
import Muse.Dock
import Muse.Cloud
import DBScore.Project

DockPage {
    id: root

    objectName: "Account"
    uri: "dbscore://account"

    property int currentPage: 0
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

    central: RowLayout {
        spacing: 0

        Rectangle {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            color: ui.theme.backgroundSecondaryColor

            Column {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 2

                Rectangle {
                    width: 196
                    height: 64
                    radius: 10
                    color: ui.theme.backgroundPrimaryColor

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 10

                        Rectangle {
                            width: 36
                            height: 36
                            radius: 18
                            color: ui.theme.accentColor

                            StyledTextLabel {
                                anchors.centerIn: parent
                                text: accountModel.phoneLoggedIn ? "🎵" : "👤"
                                font: ui.theme.largeBodyFont
                            }
                        }

                        ColumnLayout {
                            spacing: 2

                            StyledTextLabel {
                                text: accountModel.phoneLoggedIn
                                      ? (accountModel.phoneNickname.length > 0 ? accountModel.phoneNickname : accountModel.phoneMasked)
                                      : qsTrc("appshell", "未登录")
                                font: ui.theme.bodyFont
                            }

                            StyledTextLabel {
                                visible: accountModel.phoneLoggedIn
                                text: accountModel.phoneMasked
                                font: ui.theme.bodyFont
                                opacity: 0.6
                            }
                        }
                    }
                }

                Flickable {
                    width: 196
                    height: parent.height - 76
                    contentWidth: width
                    contentHeight: navContent.implicitHeight
                    clip: true

                    Column {
                        id: navContent
                        width: parent.width
                        spacing: 2

                        StyledTextLabel {
                            text: qsTrc("appshell", "账户")
                            font: ui.theme.bodyFont
                            opacity: 0.5
                            leftPadding: 8
                            topPadding: 10
                            bottomPadding: 4
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "账号概览")
                            accentButton: root.currentPage === 0
                            onClicked: root.currentPage = 0
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "我的会员")
                            accentButton: root.currentPage === 1
                            onClicked: root.currentPage = 1
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "订单记录")
                            accentButton: root.currentPage === 2
                            onClicked: root.currentPage = 2
                        }

                        StyledTextLabel {
                            text: qsTrc("appshell", "作品")
                            font: ui.theme.bodyFont
                            opacity: 0.5
                            leftPadding: 8
                            topPadding: 10
                            bottomPadding: 4
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "我的工程")
                            accentButton: root.currentPage === 3
                            onClicked: root.currentPage = 3
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "我的乐谱")
                            accentButton: root.currentPage === 4
                            onClicked: root.currentPage = 4
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "制谱记录")
                            accentButton: root.currentPage === 5
                            onClicked: root.currentPage = 5
                        }

                        StyledTextLabel {
                            text: qsTrc("appshell", "成长")
                            font: ui.theme.bodyFont
                            opacity: 0.5
                            leftPadding: 8
                            topPadding: 10
                            bottomPadding: 4
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "积分中心")
                            accentButton: root.currentPage === 6
                            onClicked: root.currentPage = 6
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "推广赚佣")
                            accentButton: root.currentPage === 7
                            onClicked: root.currentPage = 7
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "软件分享")
                            accentButton: root.currentPage === 8
                            onClicked: root.currentPage = 8
                        }

                        StyledTextLabel {
                            text: qsTrc("appshell", "支持")
                            font: ui.theme.bodyFont
                            opacity: 0.5
                            leftPadding: 8
                            topPadding: 10
                            bottomPadding: 4
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "帮助中心")
                            accentButton: root.currentPage === 9
                            onClicked: root.currentPage = 9
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "联系客服")
                            accentButton: root.currentPage === 10
                            onClicked: root.currentPage = 10
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: ui.theme.backgroundPrimaryColor

            StackLayout {
                anchors.fill: parent
                currentIndex: root.currentPage

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "账号概览")

                        PageCard {
                            visible: !accountModel.phoneLoggedIn

                            ColumnLayout {
                                spacing: 12

                                StyledTextLabel {
                                    text: qsTrc("appshell", "手机号登录")
                                    font: ui.theme.largeBodyBoldFont
                                }

                                StyledTextLabel {
                                    text: qsTrc("appshell", "未注册手机号将自动注册，注册即送3天免费试用")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }

                                RowLayout {
                                    spacing: 10

                                    StyledTextLabel { text: qsTrc("appshell", "手机号"); font: ui.theme.bodyFont }
                                    TextField {
                                        id: phoneField
                                        Layout.preferredWidth: 190
                                        placeholderText: qsTrc("appshell", "请输入手机号")
                                        inputMethodHints: Qt.ImhDigitsOnly
                                    }
                                    StyledTextLabel { text: qsTrc("appshell", "验证码"); font: ui.theme.bodyFont }
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
                                    text: accountModel.lastError
                                    color: ui.theme.accentColor
                                    font: ui.theme.bodyFont
                                    wrapMode: Text.WordWrap
                                }

                                StyledTextLabel {
                                    visible: accountModel.sendCodeMessage.length > 0
                                    text: accountModel.sendCodeMessage
                                    color: ui.theme.fontPrimaryColor
                                    font: ui.theme.bodyFont
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }

                        PageCard {
                            visible: accountModel.phoneLoggedIn

                            RowLayout {
                                spacing: 16

                                Rectangle {
                                    width: 56
                                    height: 56
                                    radius: 28
                                    color: ui.theme.accentColor
                                    StyledTextLabel {
                                        anchors.centerIn: parent
                                        text: "🎵"
                                        font: ui.theme.largeBodyFont
                                    }
                                }

                                ColumnLayout {
                                    spacing: 4
                                    StyledTextLabel {
                                        text: accountModel.phoneNickname.length > 0 ? accountModel.phoneNickname : accountModel.phoneMasked
                                        font: ui.theme.largeBodyBoldFont
                                    }
                                    StyledTextLabel {
                                        text: accountModel.phoneMasked
                                        font: ui.theme.bodyFont
                                        opacity: 0.7
                                    }
                                }

                                Item { Layout.fillWidth: true }

                                FlatButton {
                                    text: qsTrc("appshell", "退出登录")
                                    onClicked: accountModel.logout()
                                }
                            }
                        }

                        PageCard {
                            RowLayout {
                                spacing: 16

                                ColumnLayout {
                                    spacing: 6
                                    StyledTextLabel {
                                        text: qsTrc("appshell", "会员状态")
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
                                    visible: accountModel.licenseState !== 3
                                    text: qsTrc("appshell", "开通会员 ¥199/年")
                                    accentButton: true
                                    onClicked: accountModel.openPurchasePage()
                                }
                                FlatButton {
                                    visible: accountModel.licenseState === 3
                                    text: qsTrc("appshell", "续费 ¥199/年")
                                    accentButton: true
                                    onClicked: accountModel.openPurchasePage()
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "我的会员")

                        PageCard {
                            RowLayout {
                                spacing: 16
                                ColumnLayout {
                                    spacing: 6
                                    StyledTextLabel {
                                        text: qsTrc("appshell", "会员状态")
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
                                    visible: accountModel.licenseState !== 3
                                    text: qsTrc("appshell", "开通会员 ¥199/年")
                                    accentButton: true
                                    onClicked: accountModel.openPurchasePage()
                                }
                                FlatButton {
                                    visible: accountModel.licenseState === 3
                                    text: qsTrc("appshell", "续费 ¥199/年")
                                    accentButton: true
                                    onClicked: accountModel.openPurchasePage()
                                }
                            }
                        }

                        PageCard {
                            ColumnLayout {
                                spacing: 8
                                StyledTextLabel {
                                    text: qsTrc("appshell", "会员专属权益")
                                    font: ui.theme.largeBodyBoldFont
                                }
                                StyledTextLabel { text: qsTrc("appshell", "✅ 导入音频并与曲谱AI对齐"); font: ui.theme.bodyFont }
                                StyledTextLabel { text: qsTrc("appshell", "✅ 生成并导出动态.dbscore工程文件"); font: ui.theme.bodyFont }
                                StyledTextLabel { text: qsTrc("appshell", "✅ 批量导出MP4视频（1080P/2K/4K）"); font: ui.theme.bodyFont }
                                StyledTextLabel { text: qsTrc("appshell", "✅ 无水印输出文件"); font: ui.theme.bodyFont }
                                StyledTextLabel { text: qsTrc("appshell", "✅ 工程云备份与云端乐谱"); font: ui.theme.bodyFont }
                            }
                        }

                        PageCard {
                            RowLayout {
                                spacing: 10
                                StyledTextLabel { text: qsTrc("appshell", "激活码"); font: ui.theme.bodyFont }
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
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "订单记录")
                        PageCard {
                            ColumnLayout {
                                spacing: 8
                                StyledTextLabel {
                                    text: qsTrc("appshell", "暂无订单记录")
                                    font: ui.theme.largeBodyFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "开通会员后，订单记录会显示在这里。")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }
                                FlatButton {
                                    text: qsTrc("appshell", "开通会员")
                                    accentButton: true
                                    onClicked: accountModel.openPurchasePage()
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "我的工程")

                        PageCard {
                            ColumnLayout {
                                spacing: 8
                                StyledTextLabel {
                                    text: qsTrc("appshell", "本地工程")
                                    font: ui.theme.largeBodyBoldFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "以下是你最近打开过的工程文件。")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }
                            }
                        }

                        PageCard {
                            RecentScoresModel {
                                id: recentProjectsModel
                            }

                            ListView {
                                id: projectsList
                                model: recentProjectsModel
                                width: parent.width
                                implicitHeight: Math.min(420, projectsList.count * 56)
                                clip: true

                                delegate: Rectangle {
                                    width: ListView.view.width
                                    height: 56
                                    color: "transparent"

                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.margins: 8
                                        spacing: 12

                                        StyledTextLabel {
                                            Layout.fillWidth: true
                                            text: score.name || score.path || ""
                                            font: ui.theme.bodyFont
                                            elide: Text.ElideMiddle
                                        }

                                        StyledTextLabel {
                                            text: score.timeSinceModified || ""
                                            font: ui.theme.bodyFont
                                            opacity: 0.6
                                        }
                                    }
                                }
                            }

                            Component.onCompleted: recentProjectsModel.load()
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "我的乐谱")
                        PageCard {
                            ColumnLayout {
                                spacing: 8
                                StyledTextLabel {
                                    text: qsTrc("appshell", "云端乐谱即将上线")
                                    font: ui.theme.largeBodyFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "发布到云端的乐谱会显示在这里。")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "制谱记录")
                        PageCard {
                            ColumnLayout {
                                spacing: 8
                                StyledTextLabel {
                                    text: qsTrc("appshell", "制谱统计")
                                    font: ui.theme.largeBodyBoldFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "你的制谱记录和统计会显示在这里。")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "积分中心")
                        PageCard {
                            ColumnLayout {
                                spacing: 8
                                StyledTextLabel {
                                    text: qsTrc("appshell", "积分功能即将上线")
                                    font: ui.theme.largeBodyFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "签到、积分明细会显示在这里。")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "推广赚佣")
                        PageCard {
                            ColumnLayout {
                                spacing: 8
                                StyledTextLabel {
                                    text: qsTrc("appshell", "邀请好友，赚取 15% 佣金")
                                    font: ui.theme.largeBodyBoldFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "好友通过你的邀请链接注册并开通会员，你将获得其付费金额的 15% 作为佣金。")
                                    font: ui.theme.bodyFont
                                    wrapMode: Text.WordWrap
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "邀请码、佣金余额将在登录后显示，接口对接中。")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "软件分享")
                        PageCard {
                            ColumnLayout {
                                spacing: 10
                                StyledTextLabel {
                                    text: qsTrc("appshell", "把 DB Score 分享给好友")
                                    font: ui.theme.largeBodyBoldFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "分享链接：")
                                    font: ui.theme.bodyFont
                                }
                                StyledTextLabel {
                                    text: "https://drumbearai.com/dbscore"
                                    font: ui.theme.bodyFont
                                    opacity: 0.8
                                }
                                FlatButton {
                                    text: qsTrc("appshell", "复制分享链接")
                                    accentButton: true
                                    onClicked: {
                                        accountModel.copyText("https://drumbearai.com/dbscore")
                                    }
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "帮助中心")
                        PageCard {
                            ColumnLayout {
                                spacing: 10
                                StyledTextLabel {
                                    text: qsTrc("appshell", "常见问题")
                                    font: ui.theme.largeBodyBoldFont
                                }
                                StyledTextLabel { text: qsTrc("appshell", "· 如何激活会员？"); font: ui.theme.bodyFont }
                                StyledTextLabel { text: qsTrc("appshell", "· 手机号无法登录怎么办？"); font: ui.theme.bodyFont }
                                StyledTextLabel { text: qsTrc("appshell", "· 如何导出无水印视频？"); font: ui.theme.bodyFont }
                                StyledTextLabel { text: qsTrc("appshell", "· 导入的音频如何与乐谱对齐？"); font: ui.theme.bodyFont }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "联系客服")
                        PageCard {
                            ColumnLayout {
                                spacing: 10
                                StyledTextLabel {
                                    text: qsTrc("appshell", "联系我们")
                                    font: ui.theme.largeBodyBoldFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "客服微信：drumbear_ai")
                                    font: ui.theme.bodyFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "客服邮箱：support@drumbearai.com")
                                    font: ui.theme.bodyFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "意见反馈功能对接中，可先通过邮箱联系我们。")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
