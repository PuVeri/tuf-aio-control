// Export bounded static evidence for the ASUS InfoHub LCD sender.
// Run against the analyzed PE with -readOnly -noanalysis. The script only
// reads the Ghidra database and writes a text export chosen by the caller.
// @category TufAio

import java.io.File;
import java.io.PrintWriter;
import java.util.LinkedHashMap;
import java.util.Map;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;

public class ExportInfoHubLcdSender extends GhidraScript {
    private static final String[][] FUNCTION_TARGETS = {
        {"0040a7e0", "DeviceMainDlg constructor and 0x64000 transfer buffer"},
        {"0040ca10", "device-arrival VID/PID/interface-0 match"},
        {"0040cb60", "arrival-time HID capability check"},
        {"004148d0", "interface-0 sleep command"},
        {"00414ff0", "worker/timer dispatcher"},
        {"004168d0", "HID enumeration caller"},
        {"00416a00", "interface-0 mode commands"},
        {"00416bc0", "interface-1 JPEG segment builder"},
        {"00421df0", "HID1/HID2 classification"},
        {"00421ed0", "440-byte interface-0 wrapper"},
        {"004223f0", "dynamic HID API loader"},
        {"00422500", "SetupAPI HID enumeration"},
        {"00422970", "target HID open and caps"},
        {"00422b00", "overlapped HID WriteFile wrapper"}
    };

    private static final String[][] STRING_TARGETS = {
        {"0052fffc", "recognized VID/PID/interface-0 path"},
        {"00530078", "CheckHIDDevice caps diagnostic"},
        {"005325d0", "EnumerateLEDDevice hid1/hid2 result"},
        {"005325fc", "LED HID2 path diagnostic"},
        {"00532618", "LED HID1 path/fw diagnostic"},
        {"0053263c", "EnumerateLEDDevice start"}
    };

    private static final String[] IMPORT_NAMES = {
        "CreateFileA", "CreateFileW", "ReadFile", "WriteFile", "CloseHandle",
        "HidD_GetAttributes", "HidD_GetPreparsedData", "HidD_FreePreparsedData",
        "HidP_GetCaps", "SetupDiGetClassDevsA", "SetupDiEnumDeviceInterfaces",
        "SetupDiGetDeviceInterfaceDetailA", "SetupDiDestroyDeviceInfoList",
        "SaveJpgImageFile", "SaveGIFImageFile"
    };

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException("expected output file argument");
        }
        File output = new File(args[0]);
        if (output.exists()) {
            throw new IllegalStateException("refusing to overwrite " + output);
        }

        Map<Address, Function> seeds = new LinkedHashMap<>();
        try (PrintWriter out = new PrintWriter(output, "UTF-8")) {
            out.println("PROGRAM\t" + currentProgram.getName());
            out.println("LANGUAGE\t" + currentProgram.getLanguageID());
            out.println("SCOPE\tread-only static InfoHub LCD-sender evidence");
            out.println();

            out.println("FUNCTION_TARGETS");
            for (String[] target : FUNCTION_TARGETS) {
                Function function = getFunctionContaining(toAddr(target[0]));
                out.printf("TARGET\t%s\t%s\t%s%n", target[0], target[1], describe(function));
                if (function != null) {
                    seeds.put(function.getEntryPoint(), function);
                }
            }
            out.println();

            out.println("STRING_XREFS");
            for (String[] target : STRING_TARGETS) {
                Address address = toAddr(target[0]);
                out.printf("STRING\t%s\t%s%n", address, target[1]);
                addReferences(out, address, seeds);
            }
            out.println();

            out.println("IMPORT_XREFS");
            for (String name : IMPORT_NAMES) {
                out.println("IMPORT\t" + name);
                SymbolIterator symbols = currentProgram.getSymbolTable().getSymbols(name);
                while (symbols.hasNext()) {
                    Symbol symbol = symbols.next();
                    out.printf("SYMBOL\t%s\t%s\t%s%n", symbol.getAddress(),
                        symbol.getSymbolType(), symbol.getParentNamespace());
                    addReferences(out, symbol.getAddress(), null);
                }
            }
            out.println();

            out.printf("FUNCTION_COUNT\t%d%n%n", seeds.size());

            DecompInterface decompiler = new DecompInterface();
            decompiler.toggleCCode(true);
            decompiler.toggleSyntaxTree(true);
            decompiler.setSimplificationStyle("decompile");
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException("decompiler could not open program");
            }
            for (Function function : seeds.values()) {
                monitor.checkCancelled();
                out.println("FUNCTION\t" + describe(function));
                out.println("CALLERS");
                ReferenceIterator callers = currentProgram.getReferenceManager()
                    .getReferencesTo(function.getEntryPoint());
                while (callers.hasNext()) {
                    Reference ref = callers.next();
                    out.printf("REF\t%s\t%s\t%s%n", ref.getFromAddress(),
                        describe(getFunctionContaining(ref.getFromAddress())), ref.getReferenceType());
                }
                out.println("CALLEES");
                for (Function callee : function.getCalledFunctions(monitor)) {
                    out.println("CALL\t" + describe(callee));
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
            decompiler.dispose();
        }
    }

    private void addReferences(PrintWriter out, Address destination,
            Map<Address, Function> seeds) {
        ReferenceIterator references = currentProgram.getReferenceManager()
            .getReferencesTo(destination);
        while (references.hasNext()) {
            Reference ref = references.next();
            Function owner = getFunctionContaining(ref.getFromAddress());
            out.printf("XREF\t%s\t%s\t%s%n", ref.getFromAddress(),
                describe(owner), ref.getReferenceType());
            if (owner != null && seeds != null) {
                seeds.put(owner.getEntryPoint(), owner);
            }
        }
    }

    private String describe(Function function) {
        return function == null ? "NO_FUNCTION" :
            function.getEntryPoint() + ":" + function.getName();
    }
}
