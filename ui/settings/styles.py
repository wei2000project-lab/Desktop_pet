"""Styles for settings pages, editors, and the save/cancel action bar."""

SETTINGS_STYLES = """
QPushButton, QPushButton:focus {
    background-color: #ffffff;
    color: #514b59;
    border: 1px solid #cfcad4;
    border-radius: 6px;
    min-height: 32px;
    padding: 0 10px;
}
QPushButton:hover {
    background-color: #ece8f2;
    border-color: #7b4ba0;
}
QPushButton:pressed {
    background-color: #e1d8e9;
    border-color: #7b4ba0;
}
QPushButton:disabled {
    background-color: #f4f2f6;
    color: #aaa4b0;
    border-color: #dedbe3;
}
QPushButton#dashboardSidebarToggle:focus {
    background-color: transparent;
    border-color: #cbc7d0;
    color: #514b59;
}
QPushButton#dashboardSidebarToggle:hover {
    background-color: #ece8f2;
    border-color: #7b4ba0;
    color: #5f2d82;
}
QPushButton#dashboardSidebarToggle:pressed {
    background-color: #e1d8e9;
    border-color: #7b4ba0;
}
#dashboardSidebar QPushButton[checkable="true"]:focus {
    background-color: transparent;
    border-color: transparent;
}
#dashboardSidebar QPushButton[checkable="true"]:hover {
    background-color: #ece8f2;
    border-color: #d4c7df;
}
#dashboardSidebar QPushButton[checkable="true"]:pressed {
    background-color: #e1d8e9;
    border-color: #7b4ba0;
}
#dashboardSidebar QPushButton[checkable="true"]:checked {
    background-color: #eadcf5;
    border-color: transparent;
}
#dashboardSidebar QPushButton[checkable="true"]:checked:hover {
    background-color: #d9c7eb;
}
#dashboardSidebar QPushButton[checkable="true"]:checked:pressed {
    background-color: #cdb0e1;
}
#settingsPageContent, QScrollArea[settingsPage="true"] {
    background-color: #f4f3f6;
    color: #24212a;
}
#settingsPageHeading {
    color: #24212a;
    font-size: 26px;
    font-weight: 650;
}
#settingsPageDescription {
    color: #625d68;
    font-size: 14px;
}
#settingsPlaceholderStatus {
    background-color: #f7f5f9;
    border: 1px solid #ded8e4;
    border-radius: 10px;
    color: #6d6673;
    padding: 18px;
}
#settingsCard {
    background-color: #faf9fb;
    border: 1px solid #e2dfe6;
    border-radius: 10px;
}
#settingsApiGroupList {
    background-color: #f7f5f9;
    border: 1px solid #ded8e4;
    border-radius: 10px;
}
QPushButton#settingsApiGroupButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: #514b59;
    padding: 8px 10px;
    text-align: left;
}
QPushButton#settingsApiGroupButton:hover {
    background-color: #efebf3;
    border-color: #d8cfdf;
}
QPushButton#settingsApiGroupButton:checked {
    background-color: #eadcf5;
    border-color: transparent;
    color: #51276d;
    font-weight: 600;
}
QPushButton#settingsApiGroupButton:pressed {
    background-color: #e1d8e9;
    border-color: #7b4ba0;
}
QPushButton#settingsApiGroupButton:checked:hover {
    background-color: #d9c7eb;
}
QPushButton#settingsApiGroupButton:checked:pressed {
    background-color: #cdb0e1;
}
#settingsApiKeyRow {
    background-color: #ffffff;
    border: 1px solid #ded8e4;
    border-radius: 9px;
}
#settingsStatusBadge {
    background-color: #eadcf5;
    border: 1px solid #d4bce7;
    border-radius: 10px;
    color: #5f2d82;
    font-size: 12px;
    font-weight: 600;
    padding: 3px 8px;
}
#settingsSummaryPrimary {
    color: #3f3944;
    font-size: 14px;
    font-weight: 500;
}
QLabel[validationError="true"] {
    color: #b3261e;
    font-weight: 600;
}
#settingsSectionTitle {
    color: #2e2932;
    font-size: 16px;
    font-weight: 600;
}
#settingsSettingLabel {
    color: #3f3944;
    font-size: 14px;
    font-weight: 600;
}
#settingsSettingDescription {
    color: #6d6673;
    font-size: 13px;
}
#settingsToggleStatus {
    color: #827a89;
    font-size: 13px;
}
#settingsToggleStatus[active="true"] {
    color: #5f2d82;
    font-weight: 600;
}
#settingsDangerCard {
    background-color: #fff8f7;
    border: 1px solid #ecd4d1;
    border-radius: 10px;
}
#settingsDangerTitle {
    color: #8f241d;
    font-size: 16px;
    font-weight: 600;
}
#settingsDangerDescription {
    color: #765b58;
    font-size: 14px;
}
#settingsCard QLabel, #settingsCard QCheckBox,
#settingsCard QRadioButton {
    color: #3f3944;
    spacing: 8px;
}
#settingsCard QSpinBox, #settingsCard QDoubleSpinBox,
#settingsCard QLineEdit, #settingsCard QComboBox {
    background-color: #ffffff;
    color: #3f3944;
    border: 1px solid #cfcad4;
    border-radius: 6px;
    min-height: 32px;
    padding-left: 8px;
}
#settingsCard QSpinBox:focus,
#settingsCard QDoubleSpinBox:focus,
#settingsCard QLineEdit:focus,
#settingsCard QComboBox:focus {
    border: 2px solid #7b4ba0;
}
QPushButton#settingsApiGroupEditButton {
    min-width: 52px;
}
QPushButton#settingsNumberStepButton {
    background-color: #ffffff;
    border: 1px solid #cfcad4;
    border-radius: 6px;
    color: #514b59;
    font-size: 18px;
    padding: 0;
}
#settingsCard QPlainTextEdit {
    background-color: #ffffff;
    color: #3f3944;
    border: 1px solid #cfcad4;
    border-radius: 6px;
    padding: 8px;
}
#settingsCard QPlainTextEdit:disabled {
    background-color: #f0edf3;
    color: #827a89;
}
QPushButton#settingsNumberStepButton:hover {
    background-color: #ece8f2;
    border-color: #7b4ba0;
}
QPushButton#settingsNumberStepButton:pressed {
    background-color: #e1d8e9;
    border-color: #7b4ba0;
}
QPushButton#settingsNumberStepButton:disabled {
    color: #aaa4b0;
    background-color: #f4f2f6;
}
#settingsActionBar {
    background-color: #f8f7f9;
    border-top: 1px solid #dedbe3;
}
#settingsChangeStatus {
    color: #716a77;
}
#settingsActionBar QPushButton {
    min-width: 78px;
    min-height: 34px;
    border-radius: 7px;
    padding: 0 12px;
}
#settingsApplyButton, #settingsApplyButton:focus {
    background-color: #704294;
    border: 1px solid #704294;
    color: #ffffff;
}
#settingsApplyButton:hover {
    background-color: #613586;
    border-color: #613586;
}
#settingsApplyButton:pressed {
    background-color: #4f246d;
    border-color: #4f246d;
}
#settingsApplyButton:disabled {
    background-color: #d7d2db;
    border-color: #d7d2db;
    color: #8e8793;
}
#settingsDangerButton, #settingsDangerButton:focus {
    background-color: #ffffff;
    border: 1px solid #b3261e;
    border-radius: 7px;
    color: #b3261e;
    min-height: 34px;
    padding: 0 12px;
}
#settingsDangerButton:hover {
    background-color: #fbe9e7;
}
#settingsDangerButton:pressed {
    background-color: #f4d9d6;
}
"""
