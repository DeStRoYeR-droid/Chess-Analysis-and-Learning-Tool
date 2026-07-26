import ui.guiPlayInterface as playInterface
import ui.debugInterface as debugInterface
import ui.guiTestInterface as testInterface

def main(debug: bool = False, mode: str = ""):
    if (debug):
        debugInterface.main()
    else:
        if (mode == ""):
            playInterface.main()
        elif (mode == "test"):
            testInterface.main()