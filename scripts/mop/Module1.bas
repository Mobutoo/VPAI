Attribute VB_Name = "Module1"
' MOP Search Macro — Module1.bas
' Import into Excel: Alt+F11 → Insert → Module (or File → Import File)
' Requires: 'index' sheet populated from mops-index.csv (Power Query or manual paste)
' Usage: Enter keyword in recherche!B2, run SearchMOP (button or Alt+F8)

Sub SearchMOP()
    Dim keyword As String
    Dim idxSheet As Worksheet, resSheet As Worksheet
    Dim lastRow As Long, i As Long, resRow As Long

    keyword = LCase(Trim(Worksheets("recherche").Range("B2").Value))
    If keyword = "" Then
        MsgBox "Entrez un mot-clé en B2.", vbExclamation, "Recherche MOP"
        Exit Sub
    End If

    Set idxSheet = Worksheets("index")
    Set resSheet = Worksheets("recherche")

    ' Clear previous results (rows 5 to 200)
    resSheet.Range("A5:F200").ClearContents

    lastRow = idxSheet.Cells(idxSheet.Rows.Count, 1).End(xlUp).Row
    resRow = 5

    For i = 2 To lastRow
        Dim titleVal As String
        Dim keywordsVal As String
        titleVal = LCase(idxSheet.Cells(i, 2).Value)   ' column B: title
        keywordsVal = LCase(idxSheet.Cells(i, 3).Value) ' column C: keywords

        If InStr(1, keywordsVal, keyword) > 0 _
           Or InStr(1, titleVal, keyword) > 0 Then

            resSheet.Cells(resRow, 1).Value = idxSheet.Cells(i, 1).Value  ' id
            resSheet.Cells(resRow, 2).Value = idxSheet.Cells(i, 2).Value  ' title
            resSheet.Cells(resRow, 3).Value = idxSheet.Cells(i, 3).Value  ' keywords
            resSheet.Cells(resRow, 4).Value = idxSheet.Cells(i, 4).Value  ' severity
            resSheet.Cells(resRow, 5).Value = idxSheet.Cells(i, 6).Value  ' filename
            ' Clickable hyperlink to open PDF
            Dim fileUrl As String
            fileUrl = idxSheet.Cells(i, 6).Value
            If fileUrl <> "" Then
                resSheet.Cells(resRow, 6).Formula = "=HYPERLINK(""" & fileUrl & """,""Ouvrir"")"
            End If
            resRow = resRow + 1
        End If
    Next i

    Dim found As Long
    found = resRow - 5
    If found = 0 Then
        MsgBox "Aucun MOP trouvé pour : " & keyword, vbInformation, "Recherche MOP"
    Else
        MsgBox found & " MOP trouvé(s) pour : " & keyword, vbInformation, "Recherche MOP"
    End If
End Sub


Sub AddSearchButton()
    ' Run once to add the "Chercher" button on the recherche sheet
    ' The button calls SearchMOP when clicked
    Dim ws As Worksheet
    Set ws = Worksheets("recherche")

    Dim btn As Object
    Set btn = ws.Buttons.Add(ws.Range("C2").Left, ws.Range("C2").Top, 80, 22)
    btn.Caption = "Chercher"
    btn.OnAction = "SearchMOP"
End Sub
