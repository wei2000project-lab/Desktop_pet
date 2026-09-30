"""Window shell and sidebar styles, independent of page contents."""

DASHBOARD_STYLES = """
QMainWindow, #dashboardCentralWidget, #dashboardContentContainer {
    background-color: #ffffff;
    color: #24212a;
}
#dashboardContentStack {
    background-color: #f4f3f6;
    color: #24212a;
}
#dashboardSidebar {
    background-color: #f6f5f8;
    border-right: 1px solid #dedbe3;
}
#dashboardSidebarTitle {
    color: #24212a;
    font-size: 16px;
    font-weight: 600;
}
QPushButton#dashboardSidebarToggle {
    background-color: transparent;
    border: 1px solid #cbc7d0;
    border-radius: 7px;
    color: #514b59;
    font-size: 20px;
}
QPushButton#dashboardSidebarToggle:hover,
QPushButton#dashboardSidebarToggle:focus {
    background-color: #ece8f2;
    border-color: #7b4ba0;
    color: #5f2d82;
}
#dashboardSidebar QPushButton[checkable="true"] {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: #514b59;
    padding: 8px 10px;
    text-align: left;
}
#dashboardSidebar QPushButton[checkable="true"]:hover,
#dashboardSidebar QPushButton[checkable="true"]:focus {
    background-color: #ece8f2;
    border-color: #d4c7df;
}
#dashboardSidebar QPushButton[checkable="true"]:checked {
    background-color: #eadcf5;
    border-color: #9b69bd;
    color: #51276d;
    font-weight: 600;
}
"""
