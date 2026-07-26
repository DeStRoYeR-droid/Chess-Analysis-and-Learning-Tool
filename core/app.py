import ui.guiPlayInterface as playInterface
import ui.debugInterface as debugInterface

def main(debug: bool = False, mode: str = ""):
    if (debug):
        debugInterface.main()
    else:
        import ui.guiPlayInterface as playInterface
        import ui.guiTestInterface as testInterface
        if (mode == ""):
            playInterface.main()
        elif (mode == "test"):
            testInterface.main()