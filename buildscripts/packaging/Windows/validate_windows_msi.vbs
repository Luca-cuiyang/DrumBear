Option Explicit

If WScript.Arguments.Count <> 4 Then
    WScript.Echo "usage: validate_windows_msi.vbs package.msi product_name upgrade_code version"
    WScript.Quit 2
End If

Dim msi, expectedName, expectedUpgradeCode, expectedVersion
msi = WScript.Arguments(0)
expectedName = WScript.Arguments(1)
expectedUpgradeCode = UCase(WScript.Arguments(2))
expectedVersion = WScript.Arguments(3)

If Not IsValidGuid(expectedUpgradeCode) Then Fail "invalid expected upgrade code"

On Error Resume Next
Dim installer, database
Set installer = CreateObject("WindowsInstaller.Installer")
Set database = installer.OpenDatabase(msi, 0)
If Err.Number <> 0 Then Fail "cannot open MSI: " & Err.Description
On Error GoTo 0

Dim productCode, upgradeCode, productName, productVersion, allUsers, secureProperties, taskCommand
Dim uiMode
productCode = PropertyValue(database, "ProductCode")
upgradeCode = PropertyValue(database, "UpgradeCode")
productName = PropertyValue(database, "ProductName")
productVersion = PropertyValue(database, "ProductVersion")
allUsers = PropertyValue(database, "ALLUSERS")
uiMode = PropertyValue(database, "WixUI_Mode")
secureProperties = PropertyValue(database, "SecureCustomProperties")
taskCommand = ScalarValue(database, "SELECT Target FROM CustomAction WHERE Action = 'SetRegisterUpdateTask'")

If Not IsValidGuid(productCode) Then Fail "invalid ProductCode: " & productCode
If UCase(productCode) = "{00000000-0000-0000-0000-000000000000}" Then Fail "ProductCode is the zero placeholder"
If UCase(productCode) = expectedUpgradeCode Then Fail "ProductCode and UpgradeCode must differ"
If UCase(upgradeCode) <> expectedUpgradeCode Then Fail "unexpected UpgradeCode: " & upgradeCode
If InStr(1, productName, expectedName, vbTextCompare) <> 1 Then Fail "unexpected ProductName: " & productName
If InStr(1, productVersion, expectedVersion & ".", vbTextCompare) <> 1 Then Fail "unexpected ProductVersion: " & productVersion
If allUsers <> "1" Then Fail "ALLUSERS must be 1"
If uiMode <> "Minimal" Then Fail "installer must use the fixed-directory minimal UI"
If InStr(1, ";" & secureProperties & ";", ";INSTALL_ROOT;", vbTextCompare) <> 0 Then
    Fail "INSTALL_ROOT must not be an overridable secure property"
End If
If InStr(1, taskCommand, "--install-args", vbTextCompare) <> 0 Then
    Fail "the update registration must not override the install directory"
End If

If Not RowExists(database, "SELECT UpgradeCode FROM Upgrade WHERE UpgradeCode = '" & expectedUpgradeCode & "'") Then
    Fail "Upgrade table does not contain the expected UpgradeCode"
End If

If Not RowExists(database, "SELECT Action FROM CustomAction WHERE Action = 'SetRegisterUpdateTask'") Then
    Fail "SetRegisterUpdateTask custom action is missing"
End If
If Not RowExists(database, "SELECT Action FROM CustomAction WHERE Action = 'RegisterUpdateTask'") Then
    Fail "RegisterUpdateTask custom action is missing"
End If

WScript.Echo "MSI validation passed"
WScript.Echo "ProductCode=" & productCode
WScript.Echo "UpgradeCode=" & upgradeCode
WScript.Echo "ProductName=" & productName
WScript.Echo "ProductVersion=" & productVersion
WScript.Quit 0

Sub Fail(message)
    WScript.Echo "MSI validation failed: " & message
    WScript.Quit 1
End Sub

Function PropertyValue(db, propertyName)
    Dim view, record, result
    result = ""
    On Error Resume Next
    Set view = db.OpenView("SELECT Value FROM Property WHERE Property = '" & propertyName & "'")
    If Err.Number = 0 Then
        view.Execute
        If Err.Number = 0 Then
            Set record = view.Fetch
            If Err.Number = 0 And Not record Is Nothing Then result = record.StringData(1)
        End If
        view.Close
    End If
    On Error GoTo 0
    PropertyValue = result
End Function

Function RowExists(db, sql)
    Dim view, record
    RowExists = False
    On Error Resume Next
    Set view = db.OpenView(sql)
    If Err.Number = 0 Then
        view.Execute
        If Err.Number = 0 Then
            Set record = view.Fetch
            If Err.Number = 0 And Not record Is Nothing Then RowExists = True
        End If
        view.Close
    End If
    On Error GoTo 0
End Function

Function ScalarValue(db, sql)
    Dim view, record, result
    result = ""
    On Error Resume Next
    Set view = db.OpenView(sql)
    If Err.Number = 0 Then
        view.Execute
        If Err.Number = 0 Then
            Set record = view.Fetch
            If Err.Number = 0 And Not record Is Nothing Then result = record.StringData(1)
        End If
        view.Close
    End If
    On Error GoTo 0
    ScalarValue = result
End Function

Function IsValidGuid(value)
    Dim expression
    Set expression = New RegExp
    expression.IgnoreCase = True
    expression.Pattern = "^\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}$"
    IsValidGuid = expression.Test(value)
End Function
