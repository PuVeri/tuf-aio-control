// Export the bounded XYUI path that produces LEDModeCtrl's JPEG byte buffer.
// Run with -readOnly -noanalysis; no DLL code is executed.
// @category TufAio

import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayDeque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;

public class ExportInfoHubXyuiJpeg extends GhidraScript {
    private static final String[][] TARGETS = {
        {"10050610", "LEDModeCtrl constructor"},
        {"10050530", "image/jpeg encoder CLSID lookup"},
        {"10050bd0", "LEDModeCtrl destructor"},
        {"10051430", "LEDModeCtrl::SetFileImage"},
        {"10052030", "LEDModeCtrl::GetLEDData"},
        {"10052930", "LEDModeCtrl::DrawHideControl JPEG producer"},
        {"10053b80", "LEDModeCtrl::DrawControl"},
        {"10053e90", "LEDModeCtrl::DrawFrame"},
        {"10054030", "LEDModeCtrl::DrawFrame(rect)"},
        {"10057e20", "LEDModeCtrl::DrawFileMode"},
        {"10058020", "LEDModeCtrl::DrawCurrentFrame"},
        {"10058100", "LEDModeCtrl::OnControlTimer"},
        {"10054e30", "LEDModeCtrl::CreateARGB32Bitmap"},
        {"10056620", "HBITMAP-to-GDI+ bitmap wrapper"}
    };

    private static final String[] IMPORTS = {
        "GdipSaveImageToStream", "GdipSaveImageToFile", "imwrite"
    };

    private static final int EXPANSION_DEPTH = 0;

    private static class QueueItem {
        final Function function;
        final int depth;

        QueueItem(Function function, int depth) {
            this.function = function;
            this.depth = depth;
        }
    }

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
            out.println("SCOPE\tread-only static XYUI LEDModeCtrl/JPEG evidence");
            for (String[] target : TARGETS) {
                Function function = getFunctionContaining(toAddr(target[0]));
                out.printf("TARGET\t%s\t%s\t%s%n", target[0], target[1], describe(function));
                add(seeds, function);
            }
            out.println();

            for (String name : IMPORTS) {
                out.println("IMPORT\t" + name);
                SymbolIterator symbols = currentProgram.getSymbolTable().getSymbols(name);
                while (symbols.hasNext()) {
                    Symbol symbol = symbols.next();
                    out.printf("SYMBOL\t%s\t%s%n", symbol.getAddress(), symbol.getName(true));
                    ReferenceIterator refs = currentProgram.getReferenceManager()
                        .getReferencesTo(symbol.getAddress());
                    while (refs.hasNext()) {
                        Reference ref = refs.next();
                        Function owner = getFunctionContaining(ref.getFromAddress());
                        out.printf("XREF\t%s\t%s\t%s%n", ref.getFromAddress(),
                            describe(owner), ref.getReferenceType());
                    }
                }
            }
            out.println();

            Map<Address, Function> functions = expand(seeds);
            out.printf("FUNCTION_COUNT\t%d%n%n", functions.size());
            DecompInterface decompiler = new DecompInterface();
            decompiler.toggleCCode(true);
            decompiler.toggleSyntaxTree(true);
            decompiler.setSimplificationStyle("decompile");
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException("decompiler could not open program");
            }
            for (Function function : functions.values()) {
                monitor.checkCancelled();
                out.println("FUNCTION\t" + describe(function));
                out.println("CALLERS");
                ReferenceIterator refs = currentProgram.getReferenceManager()
                    .getReferencesTo(function.getEntryPoint());
                while (refs.hasNext()) {
                    Reference ref = refs.next();
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
                out.println("DECOMPILE_END\n");
            }
            decompiler.dispose();
        }
    }

    private Map<Address, Function> expand(Map<Address, Function> seeds) throws Exception {
        Map<Address, Function> result = new LinkedHashMap<>();
        ArrayDeque<QueueItem> queue = new ArrayDeque<>();
        for (Function function : seeds.values()) {
            result.put(function.getEntryPoint(), function);
            queue.addLast(new QueueItem(function, 0));
        }
        while (!queue.isEmpty()) {
            monitor.checkCancelled();
            QueueItem item = queue.removeFirst();
            if (item.depth >= EXPANSION_DEPTH) {
                continue;
            }
            Set<Function> adjacent = new LinkedHashSet<>();
            adjacent.addAll(item.function.getCalledFunctions(monitor));
            ReferenceIterator refs = currentProgram.getReferenceManager()
                .getReferencesTo(item.function.getEntryPoint());
            while (refs.hasNext()) {
                Function caller = getFunctionContaining(refs.next().getFromAddress());
                if (caller != null) {
                    adjacent.add(caller);
                }
            }
            for (Function function : adjacent) {
                if (result.put(function.getEntryPoint(), function) == null) {
                    queue.addLast(new QueueItem(function, item.depth + 1));
                }
            }
        }
        return result;
    }

    private void add(Map<Address, Function> functions, Function function) {
        if (function != null) {
            functions.put(function.getEntryPoint(), function);
        }
    }

    private String describe(Function function) {
        return function == null ? "NO_FUNCTION" :
            function.getEntryPoint() + ":" + function.getName(true);
    }
}
