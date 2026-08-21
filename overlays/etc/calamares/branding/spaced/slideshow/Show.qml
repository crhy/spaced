import QtQuick 2.0
import calamares.slideshow 1.0

Presentation {
    id: presentation

    Timer {
        interval: 7000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Slide {
        anchors.fill: parent
        Rectangle { anchors.fill: parent; color: "#17191d"; z: -1 }
        Image {
            source: "images/MacOS.png"
            anchors.fill: parent
            anchors.bottomMargin: 94
            fillMode: Image.PreserveAspectFit
            smooth: true
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: 94; color: "#e817191d"
            Text {
                anchors.centerIn: parent
                text: "Welcome to Spaced Linux 8.26.6\nFast, familiar, and free from systemd."
                color: "#f4f5f7"; font.pixelSize: 20; font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    Slide {
        anchors.fill: parent
        Rectangle { anchors.fill: parent; color: "#17191d"; z: -1 }
        Image {
            source: "images/Themes.png"
            anchors.fill: parent; anchors.bottomMargin: 100
            fillMode: Image.PreserveAspectFit; smooth: true
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: 100; color: "#e817191d"
            Text {
                anchors.centerIn: parent
                text: "Make the desktop yours\nChoose from ten complete layouts inspired by classic and modern desktops."
                color: "#f4f5f7"; font.pixelSize: 17; font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    Slide {
        anchors.fill: parent
        Rectangle { anchors.fill: parent; color: "#17191d"; z: -1 }
        Image {
            source: "images/browser.png"
            anchors.fill: parent; anchors.bottomMargin: 100
            fillMode: Image.PreserveAspectFit; smooth: true
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: 100; color: "#e817191d"
            Text {
                anchors.centerIn: parent
                text: "Browse your way\nBrave, Firefox, Chromium, communication tools, and more are ready through Flathub."
                color: "#f4f5f7"; font.pixelSize: 17; font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    Slide {
        anchors.fill: parent
        Rectangle { anchors.fill: parent; color: "#17191d"; z: -1 }
        Image {
            source: "images/wordprocess.png"
            anchors.fill: parent; anchors.bottomMargin: 100
            fillMode: Image.PreserveAspectFit; smooth: true
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: 100; color: "#e817191d"
            Text {
                anchors.centerIn: parent
                text: "Create and collaborate\nLibreOffice Writer handles documents, reports, PDFs, and Microsoft Office formats."
                color: "#f4f5f7"; font.pixelSize: 17; font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    Slide {
        anchors.fill: parent
        Rectangle { anchors.fill: parent; color: "#17191d"; z: -1 }
        Image {
            source: "images/Spreadsheet.png"
            anchors.fill: parent; anchors.bottomMargin: 100
            fillMode: Image.PreserveAspectFit; smooth: true
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: 100; color: "#e817191d"
            Text {
                anchors.centerIn: parent
                text: "Get productive\nWork with spreadsheets and presentations in LibreOffice Calc and Impress."
                color: "#f4f5f7"; font.pixelSize: 17; font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    Slide {
        anchors.fill: parent
        Rectangle { anchors.fill: parent; color: "#17191d"; z: -1 }
        Image {
            source: "images/Music.png"
            anchors.fill: parent; anchors.bottomMargin: 100
            fillMode: Image.PreserveAspectFit; smooth: true
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: 100; color: "#e817191d"
            Text {
                anchors.centerIn: parent
                text: "Your music, your player\nEnjoy Audacious, Spotify, Strawberry, and many other Linux favorites."
                color: "#f4f5f7"; font.pixelSize: 17; font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    Slide {
        anchors.fill: parent
        Rectangle { anchors.fill: parent; color: "#17191d"; z: -1 }
        Image {
            source: "images/Video.png"
            anchors.fill: parent; anchors.bottomMargin: 100
            fillMode: Image.PreserveAspectFit; smooth: true
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: 100; color: "#e817191d"
            Text {
                anchors.centerIn: parent
                text: "Entertainment that just works\nPlay videos and streams with VLC, Celluloid, Kodi, and more."
                color: "#f4f5f7"; font.pixelSize: 17; font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    Slide {
        anchors.fill: parent
        Rectangle { anchors.fill: parent; color: "#17191d"; z: -1 }
        Image {
            source: "images/ModernAItools.png"
            anchors.fill: parent; anchors.bottomMargin: 112
            fillMode: Image.PreserveAspectFit; smooth: true
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: 112; color: "#e817191d"
            Text {
                anchors.centerIn: parent
                text: "Modern tools, without the clutter\nUse voice-to-text, creative, development, gaming, and AI apps from Flathub.\nOpen SpacedBazaar after installation to explore the full catalog."
                color: "#f4f5f7"; font.pixelSize: 16; font.bold: true
                horizontalAlignment: Text.AlignHCenter
            }
        }
    }

    function onActivate() {
        presentation.currentSlide = 0
    }
}
