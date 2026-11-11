/*
 * SPDX-License-Identifier: GPL-3.0-only
 * DB Score - DB后台端账号中心
 */
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import Muse.Ui
import Muse.UiComponents
import Muse.Dock
import Muse.Interactive
import Muse.Cloud

DockPage {
    id: root

    objectName: "Account"
    uri: "dbscore://account"

    property int currentPage: 0
    property int sendCooldown: 0
    property bool avatarUpdatePending: false
    property string avatarPreviewSource: ""
    property string avatarUpdateMessage: ""

    onVisibleChanged: {
        if (visible) {
            root.refreshCurrentPage()
        }
    }

    function refreshCurrentPage() {
        if (root.currentPage <= 1) {
            accountModel.refresh()
        } else if (root.currentPage === 2) {
            accountModel.loadOrders()
        }
    }

    DbScoreAccountModel {
        id: accountModel
    }

    PaymentDialog {
        id: paymentDialog

        visible: false
        qrSource: accountModel.paymentQrSource
        planName: accountModel.paymentPlanName
        amountText: accountModel.paymentAmountText
        orderNumber: accountModel.paymentOrderNumber
        statusText: accountModel.paymentStatusText
        checking: accountModel.paymentChecking
        creating: accountModel.paymentCreating

        onCheckRequested: accountModel.checkPaymentNow()
        onClosed: accountModel.closePaymentDialog()
    }

    Connections {
        target: accountModel

        function onPaymentVisibleChanged() {
            if (accountModel.paymentVisible) {
                paymentDialog.open()
            } else {
                paymentDialog.close()
            }
        }

        function onLastErrorChanged() {
            if (root.avatarUpdatePending && accountModel.lastError.length > 0) {
                root.avatarUpdatePending = false
                root.avatarUpdateMessage = accountModel.lastError
            }
        }

        function onModelChanged() {
            if (root.avatarUpdatePending && !accountModel.busy
                    && accountModel.lastError.length === 0) {
                root.avatarUpdatePending = false
                root.avatarPreviewSource = ""
                root.avatarUpdateMessage = ""
            }
        }
    }

    FileDialog {
        id: avatarDialog
        title: qsTrc("appshell", "选择头像")
        nameFilters: [
            qsTrc("appshell", "图片 (*.jpg *.jpeg *.png *.webp)")
        ]
        onAccepted: {
            const selected = currentFile.toString()
            if (selected) {
                root.avatarUpdatePending = true
                root.avatarPreviewSource = selected
                root.avatarUpdateMessage = qsTrc("appshell", "正在更新头像…")
                accountModel.clearTransientMessages()
                accountModel.updateAvatar(selected)
            }
        }
    }

    Timer {
        interval: 1000
        repeat: true
        running: root.sendCooldown > 0
        onTriggered: {
            if (root.sendCooldown > 0) {
                root.sendCooldown -= 1
            }
        }
    }

    central: Rectangle {
        implicitWidth: 900
        implicitHeight: 700
        color: ui.theme.backgroundPrimaryColor

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 16

            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                StyledTextLabel {
                    Layout.fillWidth: true
                    text: qsTrc("appshell", "账号中心")
                    font: ui.theme.titleBoldFont
                }

                FlatButton {
                    text: qsTrc("appshell", "刷新")
                    enabled: !accountModel.busy
                    onClicked: root.refreshCurrentPage()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                FlatButton {
                    text: qsTrc("appshell", "账号概览")
                    accentButton: root.currentPage === 0
                    onClicked: {
                        root.currentPage = 0
                        accountModel.refresh()
                    }
                }
                FlatButton {
                    text: qsTrc("appshell", "我的会员")
                    accentButton: root.currentPage === 1
                    onClicked: {
                        root.currentPage = 1
                        accountModel.refresh()
                    }
                }
                FlatButton {
                    text: qsTrc("appshell", "订单记录")
                    accentButton: root.currentPage === 2
                    onClicked: {
                        root.currentPage = 2
                        accountModel.loadOrders()
                    }
                }
                Item { Layout.fillWidth: true }
            }

            StyledTextLabel {
                Layout.fillWidth: true
                visible: accountModel.lastError.length > 0
                text: accountModel.lastError
                color: ui.theme.accentColor
                font: ui.theme.bodyFont
                wrapMode: Text.WordWrap
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: root.currentPage

                // 账号概览
                Flickable {
                    clip: true
                    contentWidth: width
                    contentHeight: overviewColumn.implicitHeight

                    ColumnLayout {
                        id: overviewColumn
                        width: parent.width
                        spacing: 16

                        PageCard {
                            visible: !accountModel.phoneLoggedIn

                            ColumnLayout {
                                spacing: 12

                                StyledTextLabel {
                                    text: qsTrc("appshell", "手机号登录")
                                    font: ui.theme.largeBodyBoldFont
                                }

                                StyledTextLabel {
                                    text: qsTrc("appshell", "账号由 DB后台端统一管理，首次登录赠送 3 天试用")
                                    font: ui.theme.bodyFont
                                    opacity: 0.7
                                }

                                RowLayout {
                                    spacing: 10

                                    TextField {
                                        id: phoneField
                                        Layout.preferredWidth: 210
                                        placeholderText: qsTrc("appshell", "请输入手机号")
                                        inputMethodHints: Qt.ImhDigitsOnly
                                    }

                                    TextField {
                                        id: codeField
                                        Layout.preferredWidth: 150
                                        placeholderText: qsTrc("appshell", "6位验证码")
                                        inputMethodHints: Qt.ImhDigitsOnly
                                    }

                                    FlatButton {
                                        text: root.sendCooldown > 0
                                              ? (root.sendCooldown + qsTrc("appshell", " 秒后重发"))
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
                                        onClicked: accountModel.loginByPhone(
                                                       phoneField.text,
                                                       codeField.text)
                                    }
                                }

                                StyledTextLabel {
                                    visible: accountModel.sendCodeMessage.length > 0
                                    text: accountModel.sendCodeMessage
                                    color: "#2ECC71"
                                    font: ui.theme.bodyFont
                                }
                            }
                        }

                        PageCard {
                            visible: accountModel.phoneLoggedIn

                            RowLayout {
                                spacing: 18

                                ColumnLayout {
                                    spacing: 8

                                    Rectangle {
                                        width: 76
                                        height: 76
                                        radius: 38
                                        color: ui.theme.accentColor
                                        clip: true

                                        Image {
                                            id: avatarImage
                                            anchors.fill: parent
                                            source: root.avatarPreviewSource.length > 0
                                                    ? root.avatarPreviewSource
                                                    : accountModel.avatarUrl
                                            visible: source.toString().length > 0
                                                     && status === Image.Ready
                                            fillMode: Image.PreserveAspectCrop
                                            asynchronous: true
                                            cache: false
                                        }

                                        StyledTextLabel {
                                            anchors.centerIn: parent
                                            visible: accountModel.avatarUrl.length === 0
                                                     || avatarImage.status !== Image.Ready
                                            text: accountModel.avatarLetter
                                            font: ui.theme.titleBoldFont
                                        }
                                    }

                                    FlatButton {
                                        Layout.alignment: Qt.AlignHCenter
                                        minWidth: 76
                                        margins: 10
                                        text: root.avatarUpdatePending
                                              ? qsTrc("appshell", "正在更新头像…")
                                              : qsTrc("appshell", "更换头像")
                                        transparent: true
                                        enabled: !accountModel.busy
                                        onClicked: avatarDialog.show()
                                    }

                                    StyledTextLabel {
                                        Layout.alignment: Qt.AlignHCenter
                                        Layout.maximumWidth: 180
                                        visible: root.avatarUpdateMessage.length > 0
                                        text: root.avatarUpdateMessage
                                        color: accountModel.lastError.length > 0
                                               ? ui.theme.accentColor
                                               : ui.theme.fontPrimaryColor
                                        font: ui.theme.bodyFont
                                        horizontalAlignment: Text.AlignHCenter
                                        wrapMode: Text.WordWrap
                                    }
                                }

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 5

                                    StyledTextLabel {
                                        text: accountModel.phoneNickname.length > 0
                                              ? accountModel.phoneNickname
                                              : accountModel.phoneMasked
                                        font: ui.theme.largeBodyBoldFont
                                    }
                                    StyledTextLabel {
                                        text: qsTrc("appshell", "手机号：%1").arg(accountModel.phoneNumber)
                                        font: ui.theme.bodyFont
                                        opacity: 0.7
                                    }
                                    StyledTextLabel {
                                        text: qsTrc("appshell", "注册日期：%1").arg(accountModel.accountCreatedAtText)
                                        font: ui.theme.bodyFont
                                        opacity: 0.7
                                    }
                                    StyledTextLabel {
                                        text: accountModel.statusText
                                        font: ui.theme.bodyFont
                                    }
                                }

                                FlatButton {
                                    text: qsTrc("appshell", "退出登录")
                                    onClicked: accountModel.logout()
                                }
                            }
                        }
                    }
                }

                // 我的会员
                Flickable {
                    clip: true
                    contentWidth: width
                    contentHeight: membershipColumn.implicitHeight

                    ColumnLayout {
                        id: membershipColumn
                        width: parent.width
                        spacing: 16

                        PageCard {
                            RowLayout {
                                spacing: 16

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 5
                                    StyledTextLabel {
                                        text: qsTrc("appshell", "DB Score 会员")
                                        font: ui.theme.largeBodyBoldFont
                                    }
                                    StyledTextLabel {
                                        text: accountModel.statusText
                                        font: ui.theme.bodyFont
                                        color: accountModel.hasProAccess
                                               ? "#2ECC71"
                                               : ui.theme.accentColor
                                    }
                                }

                                FlatButton {
                                    text: accountModel.paidMembershipActive
                                          ? qsTrc("appshell", "会员续费 %1")
                                            .arg(accountModel.renewalPriceText)
                                          : qsTrc("appshell", "开通会员 %1")
                                            .arg(accountModel.renewalPriceText)
                                    accentButton: true
                                    enabled: !accountModel.busy
                                    onClicked: accountModel.openPurchasePage()
                                }
                            }
                        }

                        PageCard {
                            GridLayout {
                                columns: 2
                                columnSpacing: 48
                                rowSpacing: 12

                                StyledTextLabel { text: qsTrc("appshell", "会员类型"); opacity: 0.6 }
                                StyledTextLabel { text: accountModel.membershipKindText; font: ui.theme.bodyBoldFont }

                                StyledTextLabel { text: qsTrc("appshell", "会员方案"); opacity: 0.6 }
                                StyledTextLabel {
                                    text: accountModel.membershipPlan.length > 0
                                          ? accountModel.membershipPlan
                                          : qsTrc("appshell", "未开通")
                                    font: ui.theme.bodyBoldFont
                                }

                                StyledTextLabel { text: qsTrc("appshell", "开通日期"); opacity: 0.6 }
                                StyledTextLabel { text: accountModel.membershipStartedAtText; font: ui.theme.bodyBoldFont }

                                StyledTextLabel { text: qsTrc("appshell", "到期日期"); opacity: 0.6 }
                                StyledTextLabel { text: accountModel.membershipExpiresAtText; font: ui.theme.bodyBoldFont }

                                StyledTextLabel { text: qsTrc("appshell", "权益来源"); opacity: 0.6 }
                                StyledTextLabel { text: accountModel.membershipSourceText; font: ui.theme.bodyBoldFont }
                            }
                        }

                        StyledTextLabel {
                            Layout.fillWidth: true
                            text: qsTrc("appshell", "会员由 DB后台端统一管理，支付成功后自动更新权益和到期时间。")
                            font: ui.theme.bodyFont
                            opacity: 0.65
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                // 订单记录
                Flickable {
                    clip: true
                    contentWidth: width
                    contentHeight: ordersColumn.implicitHeight

                    ColumnLayout {
                        id: ordersColumn
                        width: parent.width
                        spacing: 12

                        StyledTextLabel {
                            visible: accountModel.ordersList.length === 0
                            text: accountModel.busy
                                  ? qsTrc("appshell", "正在加载订单…")
                                  : qsTrc("appshell", "暂无订单记录")
                            font: ui.theme.bodyFont
                            opacity: 0.7
                        }

                        PageCard {
                            ColumnLayout {
                                spacing: 0

                                Repeater {
                                    model: accountModel.ordersList

                                    delegate: RowLayout {
                                        required property var modelData
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 54
                                        spacing: 12

                                        StyledTextLabel {
                                            Layout.fillWidth: true
                                            text: (modelData.product
                                                   ? modelData.product + " · "
                                                   : "")
                                                  + (modelData.planName
                                                     || modelData.orderNo
                                                     || qsTrc("appshell", "会员订单"))
                                            font: ui.theme.bodyFont
                                            elide: Text.ElideMiddle
                                        }
                                        StyledTextLabel {
                                            text: "¥" + ((modelData.amountCents || 0) / 100).toFixed(2)
                                            font: ui.theme.bodyFont
                                        }
                                        StyledTextLabel {
                                            Layout.preferredWidth: 76
                                            text: modelData.sourceLabel
                                                  || qsTrc("appshell", "历史订单")
                                            font: ui.theme.bodyFont
                                            opacity: 0.72
                                        }
                                        StyledTextLabel {
                                            text: modelData.status === "paid"
                                                  ? qsTrc("appshell", "已支付")
                                                  : modelData.status === "pending"
                                                    ? qsTrc("appshell", "待支付")
                                                    : modelData.status === "refunded"
                                                      ? qsTrc("appshell", "已退款")
                                                      : qsTrc("appshell", "已关闭")
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
    }
}
