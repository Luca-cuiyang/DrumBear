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

    onCurrentPageChanged: {
        if (root.currentPage === 0 || root.currentPage === 1) {
            accountModel.refresh()
        } else if (root.currentPage === 2) {
            accountModel.loadOrders()
        } else if (root.currentPage === 3) {
            accountModel.loadProjects()
        } else if (root.currentPage === 4) {
            accountModel.loadScores()
        } else if (root.currentPage === 6) {
            accountModel.loadPoints()
        } else if (root.currentPage === 7) {
            accountModel.loadInvite()
        } else if (root.currentPage === 12) {
            accountModel.loadNotifications()
        }
    }

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
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "软件更新")
                            accentButton: root.currentPage === 11
                            onClicked: root.currentPage = 11
                        }
                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "通知中心")
                            accentButton: root.currentPage === 12
                            onClicked: root.currentPage = 12
                        }

                        Rectangle {
                            width: parent.width
                            height: 1
                            color: ui.theme.strokeColor
                        }

                        FlatButton {
                            width: parent.width
                            text: qsTrc("appshell", "设置")
                            accentButton: root.currentPage === 13
                            onClicked: root.currentPage = 13
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

                        StyledTextLabel {
                            visible: accountModel.ordersList.length === 0
                            text: qsTrc("appshell", "暂无订单记录")
                            font: ui.theme.bodyFont
                            opacity: 0.7
                        }

                        PageCard {
                            ColumnLayout {
                                spacing: 0

                                Repeater {
                                    model: accountModel.ordersList

                                    delegate: RowLayout {
                                        width: parent ? parent.width : 0
                                        height: 48
                                        spacing: 12

                                        StyledTextLabel {
                                            Layout.fillWidth: true
                                            text: modelData.planName || modelData.orderNo || ""
                                            font: ui.theme.bodyFont
                                            elide: Text.ElideMiddle
                                        }

                                        StyledTextLabel {
                                            text: "¥" + ((modelData.amountCents || 0) / 100).toFixed(2)
                                            font: ui.theme.bodyFont
                                        }

                                        StyledTextLabel {
                                            text: modelData.status === "paid" ? qsTrc("appshell", "已支付")
                                                  : modelData.status === "pending" ? qsTrc("appshell", "待支付")
                                                  : qsTrc("appshell", "已取消")
                                            font: ui.theme.bodyFont
                                            opacity: 0.7
                                        }
                                    }
                                }
                            }
                        }

                        FlatButton {
                            text: qsTrc("appshell", "开通会员")
                            accentButton: true
                            onClicked: accountModel.openPurchasePage()
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

                        PageCard {
                            ColumnLayout {
                                spacing: 8

                                StyledTextLabel {
                                    text: qsTrc("appshell", "云端备份")
                                    font: ui.theme.largeBodyBoldFont
                                }

                                StyledTextLabel {
                                    visible: accountModel.projectsList.length === 0
                                    text: qsTrc("appshell", "暂无云端备份的工程。")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }

                                Repeater {
                                    model: accountModel.projectsList

                                    delegate: RowLayout {
                                        width: parent ? parent.width : 0
                                        height: 44
                                        spacing: 12

                                        StyledTextLabel {
                                            Layout.fillWidth: true
                                            text: modelData.name || ""
                                            font: ui.theme.bodyFont
                                            elide: Text.ElideMiddle
                                        }

                                        StyledTextLabel {
                                            text: modelData.size ? (modelData.size / 1048576).toFixed(1) + " MB" : ""
                                            font: ui.theme.bodyFont
                                            opacity: 0.6
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "我的乐谱")

                        StyledTextLabel {
                            visible: accountModel.scoresList.length === 0
                            text: qsTrc("appshell", "暂无云端乐谱，发布乐谱后会显示在这里。")
                            font: ui.theme.bodyFont
                            opacity: 0.7
                        }

                        PageCard {
                            ColumnLayout {
                                spacing: 0

                                Repeater {
                                    model: accountModel.scoresList

                                    delegate: RowLayout {
                                        width: parent ? parent.width : 0
                                        height: 48
                                        spacing: 12

                                        StyledTextLabel {
                                            Layout.fillWidth: true
                                            text: modelData.title || modelData.name || ""
                                            font: ui.theme.bodyFont
                                            elide: Text.ElideMiddle
                                        }

                                        StyledTextLabel {
                                            text: modelData.visibility === "private"
                                                  ? qsTrc("appshell", "私密")
                                                  : qsTrc("appshell", "公开")
                                            font: ui.theme.bodyFont
                                            opacity: 0.7
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "制谱记录")

                        PageCard {
                            RecentScoresModel {
                                id: recordsModel
                            }

                            ColumnLayout {
                                spacing: 6

                                StyledTextLabel {
                                    text: qsTrc("appshell", "最近制谱")
                                    font: ui.theme.largeBodyBoldFont
                                }

                                StyledTextLabel {
                                    text: qsTrc("appshell", "累计制谱数量：") + recordsModel.rowCount
                                    font: ui.theme.bodyFont
                                }

                                Repeater {
                                    model: recordsModel

                                    delegate: RowLayout {
                                        width: parent ? parent.width : 0
                                        height: 44
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

                            Component.onCompleted: recordsModel.load()
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "积分中心")
                        PageCard {
                            RowLayout {
                                spacing: 16

                                ColumnLayout {
                                    spacing: 4
                                    StyledTextLabel {
                                        text: qsTrc("appshell", "当前积分")
                                        font: ui.theme.bodyFont
                                        opacity: 0.7
                                    }
                                    StyledTextLabel {
                                        text: accountModel.pointsBalance
                                        font: ui.theme.titleBoldFont
                                    }
                                }

                                Item { Layout.fillWidth: true }

                                FlatButton {
                                    visible: !accountModel.todayCheckedIn
                                    text: qsTrc("appshell", "每日签到")
                                    accentButton: true
                                    enabled: !accountModel.busy
                                    onClicked: accountModel.checkIn()
                                }
                                StyledTextLabel {
                                    visible: accountModel.todayCheckedIn
                                    text: qsTrc("appshell", "今日已签到")
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
                                spacing: 10
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
                                    visible: !accountModel.phoneLoggedIn
                                    text: qsTrc("appshell", "登录后查看你的邀请码和佣金。")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }

                                ColumnLayout {
                                    visible: accountModel.phoneLoggedIn
                                    spacing: 6

                                    StyledTextLabel {
                                        text: qsTrc("appshell", "邀请码：") + accountModel.inviteCode
                                        font: ui.theme.bodyFont
                                    }
                                    StyledTextLabel {
                                        text: qsTrc("appshell", "佣金余额：¥") + (accountModel.commissionBalanceCents / 100).toFixed(2)
                                        font: ui.theme.bodyFont
                                    }
                                    StyledTextLabel {
                                        text: qsTrc("appshell", "累计赚取：¥") + (accountModel.totalEarnedCents / 100).toFixed(2)
                                        font: ui.theme.bodyFont
                                    }
                                    StyledTextLabel {
                                        text: qsTrc("appshell", "已邀请好友：") + accountModel.inviteeCount + qsTrc("appshell", " 人")
                                        font: ui.theme.bodyFont
                                    }
                                }

                                FlatButton {
                                    visible: accountModel.phoneLoggedIn && accountModel.inviteUrl.length > 0
                                    text: qsTrc("appshell", "复制邀请链接")
                                    accentButton: true
                                    onClicked: accountModel.copyText(accountModel.inviteUrl)
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
                            }
                        }

                        PageCard {
                            ColumnLayout {
                                spacing: 10

                                StyledTextLabel {
                                    text: qsTrc("appshell", "意见反馈")
                                    font: ui.theme.largeBodyBoldFont
                                }

                                TextField {
                                    id: feedbackContact
                                    Layout.fillWidth: true
                                    placeholderText: qsTrc("appshell", "联系方式（选填）")
                                }

                                TextArea {
                                    id: feedbackContent
                                    Layout.fillWidth: true
                                    height: 100
                                    placeholderText: qsTrc("appshell", "请描述你的问题或建议…")
                                }

                                StyledTextLabel {
                                    visible: accountModel.lastError.length > 0
                                    text: accountModel.lastError
                                    color: ui.theme.accentColor
                                    font: ui.theme.bodyFont
                                    wrapMode: Text.WordWrap
                                }

                                FlatButton {
                                    text: qsTrc("appshell", "提交反馈")
                                    accentButton: true
                                    enabled: !accountModel.busy
                                    onClicked: accountModel.submitFeedback(feedbackContent.text, feedbackContact.text)
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "软件更新")

                        PageCard {
                            ColumnLayout {
                                spacing: 10

                                StyledTextLabel {
                                    text: qsTrc("appshell", "当前版本：") + accountModel.currentVersion
                                    font: ui.theme.bodyFont
                                }

                                StyledTextLabel {
                                    visible: accountModel.latestVersion.length > 0
                                    text: qsTrc("appshell", "最新版本：") + accountModel.latestVersion
                                    font: ui.theme.bodyFont
                                }

                                StyledTextLabel {
                                    visible: accountModel.updateNotes.length > 0
                                    text: accountModel.updateNotes
                                    font: ui.theme.bodyFont
                                    opacity: 0.8
                                    wrapMode: Text.WordWrap
                                }

                                StyledTextLabel {
                                    visible: accountModel.lastError.length > 0
                                    text: accountModel.lastError
                                    color: ui.theme.accentColor
                                    font: ui.theme.bodyFont
                                    wrapMode: Text.WordWrap
                                }

                                RowLayout {
                                    spacing: 10

                                    FlatButton {
                                        text: qsTrc("appshell", "检查更新")
                                        enabled: !accountModel.busy
                                        onClicked: accountModel.checkForUpdate()
                                    }

                                    FlatButton {
                                        visible: accountModel.updateAvailable
                                        text: qsTrc("appshell", "下载安装包")
                                        accentButton: true
                                        onClicked: accountModel.openUpdateDownload()
                                    }
                                }
                            }
                        }

                        PageCard {
                            ColumnLayout {
                                spacing: 8
                                StyledTextLabel {
                                    text: qsTrc("appshell", "如何更新")
                                    font: ui.theme.largeBodyBoldFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "点击“检查更新”，如有新版本，点击“下载安装包”下载后手动安装即可。")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "通知中心")

                        StyledTextLabel {
                            visible: accountModel.notificationsList.length === 0
                            text: qsTrc("appshell", "暂无通知")
                            font: ui.theme.bodyFont
                            opacity: 0.7
                        }

                        PageCard {
                            ColumnLayout {
                                spacing: 0

                                Repeater {
                                    model: accountModel.notificationsList

                                    delegate: ColumnLayout {
                                        width: parent ? parent.width : 0
                                        spacing: 4

                                        StyledTextLabel {
                                            Layout.fillWidth: true
                                            text: modelData.title || ""
                                            font: ui.theme.bodyFont
                                            elide: Text.ElideMiddle
                                        }

                                        StyledTextLabel {
                                            Layout.fillWidth: true
                                            text: modelData.content || ""
                                            font: ui.theme.bodyFont
                                            opacity: 0.7
                                            wrapMode: Text.WordWrap
                                            maximumLineCount: 2
                                        }

                                        Rectangle {
                                            Layout.fillWidth: true
                                            height: 1
                                            color: ui.theme.strokeColor
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Item {
                    PageFrame {
                        title: qsTrc("appshell", "设置")

                        PageCard {
                            ColumnLayout {
                                spacing: 10

                                StyledTextLabel {
                                    text: qsTrc("appshell", "关于软件")
                                    font: ui.theme.largeBodyBoldFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "当前版本：") + accountModel.currentVersion
                                    font: ui.theme.bodyFont
                                }
                                StyledTextLabel {
                                    text: qsTrc("appshell", "DB Score 制谱大师")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }
                            }
                        }

                        PageCard {
                            ColumnLayout {
                                spacing: 10

                                StyledTextLabel {
                                    text: qsTrc("appshell", "账号")
                                    font: ui.theme.largeBodyBoldFont
                                }

                                FlatButton {
                                    text: qsTrc("appshell", "刷新授权")
                                    onClicked: accountModel.refresh()
                                }

                                FlatButton {
                                    visible: accountModel.phoneLoggedIn
                                    text: qsTrc("appshell", "退出登录")
                                    onClicked: accountModel.logout()
                                }

                                FlatButton {
                                    visible: !accountModel.phoneLoggedIn
                                    text: qsTrc("appshell", "清除授权")
                                    onClicked: accountModel.clearLicense()
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
