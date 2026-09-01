// Export static evidence for the LCD large-data, renderer, and state paths.
// The project is expected to be opened with -readOnly -noanalysis. Any missing
// function created here exists only in the transient read-only session.
// @category TufAio

import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ExportLcdDataPath extends GhidraScript {
    private static final String[][] TARGETS = {
        {"0010df9c", "interface-1 endpoint-3 OUT callback"},
        {"001297e8", "1024-byte segmented receiver"},
        {"00129b2c", "large-data consumer callback"},
        {"00129d84", "protocol task and queue initialization"},
        {"001293f8", "440-byte transport initialization"},
        {"0012a250", "queue helper used after notification handling"},
        {"0012a290", "notification dequeue/peek helper"},
        {"0012a310", "large-data queue reset/release helper"},
        {"0012a390", "large-data dequeue helper"},
        {"0012a3bc", "large buffer initialization helper"},
        {"0012a3f0", "large-data queue allocation/commit helper"},
        {"0012b164", "queue service helper"},
        {"001056a4", "graphics state reset"},
        {"00106058", "graphics format/mode setter"},
        {"001060ec", "graphics transfer start"},
        {"001065c4", "graphics router"},
        {"00109388", "interface-0 graphics descriptor source"},
        {"0010f0d0", "object dimensions reader"},
        {"0010eff4", "object draw wrapper"},
        {"0010d80c", "timing arithmetic helper"},
        {"0010e3c8", "object/image decoder factory"},
        {"00110a58", "object/image header parser"},
        {"0010f16c", "object/image row fallback"},
        {"00110f74", "renderer buffer constructor"},
        {"001141e0", "renderer pixel conversion helper"},
        {"001151e4", "renderer scanline draw helper"},
        {"0011acd8", "object renderer bridge"},
        {"001279e8", "LCD display-state callback"},
        {"00127ce0", "LCD timing source callback"},
        {"001268d0", "LCD boot callback"},
        {"00127854", "default LCD configuration initializer"},
        {"00126dfc", "device command dispatcher"}
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

        try (PrintWriter out = new PrintWriter(output, "UTF-8")) {
            out.println("PROGRAM\t" + currentProgram.getName());
            out.println("LANGUAGE\t" + currentProgram.getLanguageID());
            out.println("SCOPE\tread-only static LCD data-path export; no emulation or device access");
            out.println();

            DecompInterface decompiler = new DecompInterface();
            decompiler.toggleCCode(true);
            decompiler.toggleSyntaxTree(true);
            decompiler.setSimplificationStyle("decompile");
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException("decompiler could not open program");
            }

            Set<Long> referencedPointerValues = new LinkedHashSet<>();
            for (String[] target : TARGETS) {
                monitor.checkCancelled();
                Function function = ensureFunction(target[0]);
                out.printf("TARGET\t%s\t%s\t%s%n", target[0], target[1], describe(function));
                if (function == null) {
                    out.println("FUNCTION_UNAVAILABLE");
                    out.println();
                    continue;
                }

                out.println("CALLERS");
                ReferenceIterator callers = currentProgram.getReferenceManager()
                    .getReferencesTo(function.getEntryPoint());
                while (callers.hasNext()) {
                    Reference ref = callers.next();
                    Function owner = getFunctionContaining(ref.getFromAddress());
                    out.printf("%s\t%s\t%s%n", ref.getFromAddress(), describe(owner),
                        ref.getReferenceType());
                }

                out.println("INSTRUCTIONS_AND_REFERENCES");
                AddressSetView body = function.getBody();
                for (Instruction instruction : currentProgram.getListing().getInstructions(body, true)) {
                    out.printf("I\t%s\t%s%n", instruction.getAddress(), instruction);
                    for (Reference ref : instruction.getReferencesFrom()) {
                        Address destination = ref.getToAddress();
                        out.printf("R\t%s\t%s\t%s", instruction.getAddress(), destination,
                            ref.getReferenceType());
                        Long value = readUnsignedInt(destination);
                        if (value != null) {
                            out.printf("\tDWORD=0x%08x", value);
                            if (looksLikePointer(value)) {
                                referencedPointerValues.add(value);
                            }
                        }
                        out.println();
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
            decompiler.dispose();

            out.println("POINTER_VALUE_XREFS");
            for (long value : referencedPointerValues) {
                monitor.checkCancelled();
                out.printf("POINTER\t0x%08x%n", value);
                for (Address literal : findDwordOccurrences(value)) {
                    out.printf("LITERAL\t%s%n", literal);
                    ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(literal);
                    while (refs.hasNext()) {
                        Reference ref = refs.next();
                        Function owner = getFunctionContaining(ref.getFromAddress());
                        out.printf("XREF\t%s\t%s\t%s%n", ref.getFromAddress(), describe(owner),
                            ref.getReferenceType());
                    }
                }
            }
        }
    }

    private Function ensureFunction(String text) throws Exception {
        Address address = toAddr(text);
        Function function = getFunctionAt(address);
        if (function == null) {
            function = getFunctionContaining(address);
        }
        if (function == null) {
            disassemble(address);
            function = createFunction(address, null);
        }
        return function;
    }

    private String describe(Function function) {
        return function == null ? "NO_FUNCTION" :
            function.getEntryPoint() + ":" + function.getName();
    }

    private Long readUnsignedInt(Address address) {
        Memory memory = currentProgram.getMemory();
        try {
            if (!memory.contains(address) || !memory.contains(address.add(3))) {
                return null;
            }
            return Integer.toUnsignedLong(memory.getInt(address));
        }
        catch (Exception ignored) {
            return null;
        }
    }

    private boolean looksLikePointer(long value) {
        return (value >= 0x00100000L && value < 0x00500000L);
    }

    private List<Address> findDwordOccurrences(long wanted) throws Exception {
        List<Address> result = new ArrayList<>();
        Memory memory = currentProgram.getMemory();
        Address start = currentProgram.getMinAddress();
        Address end = currentProgram.getMaxAddress();
        Address cursor = start;
        while (cursor.compareTo(end) <= 0 && cursor.add(3).compareTo(end) <= 0) {
            monitor.checkCancelled();
            if ((cursor.getOffset() & 3) == 0 && memory.contains(cursor) &&
                Integer.toUnsignedLong(memory.getInt(cursor)) == wanted) {
                result.add(cursor);
            }
            cursor = cursor.add(1);
        }
        return result;
    }
}
