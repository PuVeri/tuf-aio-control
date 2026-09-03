// Read-only export for the bounded ASUS InfoHub LCD refresh call chain.
// Run only against the analyzed InfoHub 1.0.0.15 PE with -readOnly -noanalysis.
// @category TufAio

import java.io.File;
import java.io.PrintWriter;
import java.util.LinkedHashMap;
import java.util.Map;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ExportInfoHubRefreshTriage extends GhidraScript {
    private static final String EXPECTED_PROGRAM = "ASUS InfoHub.exe";
    private static final String EXPECTED_SHA256 =
        "7eeb0c61904a36f8fab3945209d8472088db8b093250387e3b06228b81d356e0";
    private static final String EXPECTED_IMAGE_BASE = "00400000";

    private static final String[][] TARGETS = {
        {"0040b103", "DeviceMainDlg init anchor that starts the 12 ms worker timer"},
        {"0040abf0", "DeviceMainDlg teardown anchor for worker-lifetime review"},
        {"00410fe0", "window-message dispatcher for WM_POWERBROADCAST and other UI events"},
        {"004119b0", "WM_POWERBROADCAST callback that changes the JPEG suppression gate"},
        {"0040cf00", "worker idle-path task gated to at most once per 2000 ms"},
        {"004148d0", "separate Interface-0 0x1f sleep action"},
        {"00414ff0", "LCD refresh worker entry"},
        {"004151d0", "worker event 0x01 handler queued during dialog initialization"},
        {"004152f0", "worker post-enumeration setup called by event 0x1b"},
        {"004168d0", "worker event 0x1b HID enumeration and connection-gate update"},
        {"00416a00", "worker event 0x1c Interface-0 0x10/0x12 action"},
        {"00416bc0", "Interface-1 0x08 JPEG sender entry"},
        {"00416de0", "worker event 0x14 handler queued during dialog initialization"},
        {"00417f50", "post-configuration UI action reached during worker initialization"},
        {"00425bc0", "recurring timer stop/wait helper"},
        {"00425c10", "recurring timer thread entry and cadence loop"}
    };

    @Override
    public void run() throws Exception {
        validateProgram();

        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("expected output file argument");
        }
        File output = new File(args[0]);
        if (output.exists()) {
            throw new IllegalStateException("refusing to overwrite " + output);
        }

        Map<Address, Function> functions = new LinkedHashMap<>();
        for (String[] target : TARGETS) {
            Function function = getFunctionContaining(toAddr(target[0]));
            if (function == null) {
                throw new IllegalStateException(
                    "no function contains target " + target[0] + " (" + target[1] + ")");
            }
            functions.put(function.getEntryPoint(), function);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.toggleCCode(true);
        decompiler.toggleSyntaxTree(true);
        decompiler.setSimplificationStyle("decompile");
        if (!decompiler.openProgram(currentProgram)) {
            throw new IllegalStateException("decompiler could not open program");
        }

        try (PrintWriter out = new PrintWriter(output, "UTF-8")) {
            out.println("PROGRAM\t" + currentProgram.getName());
            out.println("SHA256\t" + currentProgram.getExecutableSHA256());
            out.println("IMAGE_BASE\t" + currentProgram.getImageBase());
            out.println("LANGUAGE\t" + currentProgram.getLanguageID());
            out.println("SCOPE\tbounded read-only InfoHub LCD refresh-worker export");
            out.println();

            out.println("TARGETS");
            for (String[] target : TARGETS) {
                Function function = getFunctionContaining(toAddr(target[0]));
                out.printf("TARGET\t%s\t%s\t%s%n", target[0], target[1], describe(function));
            }
            out.println();

            for (Function function : functions.values()) {
                monitor.checkCancelled();
                out.println("FUNCTION\t" + describe(function));
                out.println("CALLERS");
                ReferenceIterator refs = currentProgram.getReferenceManager()
                    .getReferencesTo(function.getEntryPoint());
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    Function owner = getFunctionContaining(ref.getFromAddress());
                    out.printf("REF\t%s\t%s\t%s%n", ref.getFromAddress(),
                        describe(owner), ref.getReferenceType());
                }
                out.println("CALLEES");
                for (Function callee : function.getCalledFunctions(monitor)) {
                    out.println("CALL\t" + describe(callee));
                }
                out.println("INSTRUCTIONS_AND_REFERENCES");
                for (Instruction instruction :
                        currentProgram.getListing().getInstructions(function.getBody(), true)) {
                    out.printf("I\t%s\t%s%n", instruction.getAddress(), instruction);
                    for (Reference ref : instruction.getReferencesFrom()) {
                        out.printf("R\t%s\t%s\t%s\t%s%n", instruction.getAddress(),
                            ref.getToAddress(), ref.getReferenceType(),
                            describe(getFunctionContaining(ref.getToAddress())));
                    }
                }
                out.println("DECOMPILE_BEGIN");
                DecompileResults result = decompiler.decompileFunction(function, 180, monitor);
                if (result.decompileCompleted()) {
                    out.println(result.getDecompiledFunction().getC());
                }
                else {
                    out.println("FAILED\t" + result.getErrorMessage());
                }
                out.println("DECOMPILE_END");
                out.println();
            }
        }
        decompiler.dispose();
    }

    private void validateProgram() {
        if (!EXPECTED_PROGRAM.equals(currentProgram.getName())) {
            throw new IllegalStateException(
                "wrong program: " + currentProgram.getName() + ", expected " + EXPECTED_PROGRAM);
        }
        if (!EXPECTED_SHA256.equalsIgnoreCase(currentProgram.getExecutableSHA256())) {
            throw new IllegalStateException(
                "wrong executable SHA-256: " + currentProgram.getExecutableSHA256());
        }
        if (!toAddr(EXPECTED_IMAGE_BASE).equals(currentProgram.getImageBase())) {
            throw new IllegalStateException(
                "wrong image base: " + currentProgram.getImageBase());
        }
    }

    private String describe(Function function) {
        return function == null ? "NO_FUNCTION" :
            function.getEntryPoint() + ":" + function.getName();
    }
}
