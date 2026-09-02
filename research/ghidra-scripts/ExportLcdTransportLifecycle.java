// Export static evidence for the Host-to-LCD JPEG transport lifecycle.
// Run against the existing project with -readOnly -noanalysis.
// @category TufAio

import java.io.File;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ExportLcdTransportLifecycle extends GhidraScript {
    private static final String[][] TARGETS = {
        {"0010df9c", "Interface-1 OUT callback and queue producer"},
        {"001268d0", "protocol-side state poller"},
        {"00126dfc", "Interface-0 command dispatcher"},
        {"00127854", "protocol configuration initializer"},
        {"001279e8", "stored-object/display state task"},
        {"001297e8", "four-byte control-word consumer"},
        {"00129b2c", "assembled JPEG queue consumer"},
        {"0011508c", "Interface-1 IN sender"},
        {"0010e0a8", "Interface-1 IN completion callback"},
        {"0012a3f0", "queue allocation"},
        {"0012a390", "queue peek"},
        {"0012a310", "queue release"},
        {"001056a4", "graphics-state reset"},
        {"001059f4", "decoder dimensions"},
        {"00105a10", "decoder IRQ and transfer-state handler"},
        {"00105e3c", "blocking decoder result"},
        {"00105e60", "non-blocking decoder completion query"},
        {"001060ec", "hardware-decoder start"},
        {"001065c4", "graphics router"},
        {"00129cf0", "visible framebuffer switch"},
        {"00109394", "display framebuffer register writer"},
        {"0011acd8", "reference JPEG renderer"},
        {"001279e8", "stored-object caller supplying JPEG pointer and length"},
        {"0010eff4", "JPEG pointer and length state producer"},
        {"00110a58", "JPEG SOI/SOF validator"},
        {"0011012c", "JPEG object preparation and source-range setup"},
        {"0010f16c", "software JPEG decoder"},
        {"00124988", "JPEG marker parser"},
        {"0012bbac", "display-state helper reading transfer gate"},
        {"0012bd68", "display-state periodic-callback registrar"}
    };

    private static final long[] POINTER_VALUES = {
        0x0012eba0L, 0x003bb430L, 0x003bb480L, 0x003ed340L,
        0x00130de4L, 0x001315c4L, 0x001315ccL, 0x00131928L, 0x0013193cL,
        0x00131940L, 0x004e8348L
    };

    private static final long[] EXACT_SCALARS = {
        0x08L, 0x14L, 0x20L, 0x3fcL, 0xc8L, 0x400L,
        0x81L, 0xd8L, 0xd9L, 0x31fe0L, 0x32000L, 0x6021L
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
            out.println("SCOPE\tread-only Host-to-LCD JPEG transport lifecycle export");
            out.println();

            DecompInterface decompiler = new DecompInterface();
            decompiler.toggleCCode(true);
            decompiler.toggleSyntaxTree(true);
            decompiler.setSimplificationStyle("decompile");
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException("decompiler could not open program");
            }

            Set<Address> emitted = new LinkedHashSet<>();
            for (String[] target : TARGETS) {
                emitFunction(out, decompiler, ensureFunction(target[0]), target[1], emitted);
            }

            out.println("POINTER_LITERAL_USERS");
            for (long wanted : POINTER_VALUES) {
                out.printf("POINTER\t0x%08x%n", wanted);
                for (Address literal : findAlignedDwordOccurrences(wanted)) {
                    out.printf("LITERAL\t%s%n", literal);
                    ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(literal);
                    while (refs.hasNext()) {
                        Reference ref = refs.next();
                        Function function = getFunctionContaining(ref.getFromAddress());
                        out.printf("XREF\t%s\t%s\t%s%n", ref.getFromAddress(),
                            describe(function), ref.getReferenceType());
                        emitFunction(out, decompiler, function,
                            String.format("user of pointer 0x%08x", wanted), emitted);
                    }
                }
            }

            out.println("EXACT_SCALAR_USES");
            for (long wanted : EXACT_SCALARS) {
                out.printf("SCALAR\t0x%x\t%d%n", wanted, wanted);
                for (Instruction instruction : currentProgram.getListing().getInstructions(true)) {
                    for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
                        for (Object object : instruction.getOpObjects(operand)) {
                            if (object instanceof Scalar &&
                                ((Scalar)object).getUnsignedValue() == wanted) {
                                out.printf("USE\t%s\t%s\t%s%n", instruction.getAddress(),
                                    describe(getFunctionContaining(instruction.getAddress())), instruction);
                            }
                        }
                    }
                }
            }

            emitBytes(out, 0x0012eba0L, 16, "Interface-1 IN source template");
            decompiler.dispose();
        }
    }

    private void emitFunction(PrintWriter out, DecompInterface decompiler, Function function,
            String label, Set<Address> emitted) throws Exception {
        if (function == null || !emitted.add(function.getEntryPoint())) {
            return;
        }
        out.printf("FUNCTION\t%s\t%s%n", label, describe(function));
        out.println("CALLERS");
        ReferenceIterator callers = currentProgram.getReferenceManager()
            .getReferencesTo(function.getEntryPoint());
        while (callers.hasNext()) {
            Reference ref = callers.next();
            out.printf("%s\t%s\t%s%n", ref.getFromAddress(),
                describe(getFunctionContaining(ref.getFromAddress())), ref.getReferenceType());
        }
        out.println("CALLEES");
        for (Function callee : function.getCalledFunctions(monitor)) {
            out.println(describe(callee));
        }
        out.println("INSTRUCTIONS_AND_REFERENCES");
        AddressSetView body = function.getBody();
        for (Instruction instruction : currentProgram.getListing().getInstructions(body, true)) {
            out.printf("I\t%s\t%s%n", instruction.getAddress(), instruction);
            for (Reference ref : instruction.getReferencesFrom()) {
                out.printf("R\t%s\t%s\t%s%n", instruction.getAddress(),
                    ref.getToAddress(), ref.getReferenceType());
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

    private void emitBytes(PrintWriter out, long startValue, int length, String label)
            throws Exception {
        Address start = toAddr(startValue);
        byte[] bytes = new byte[length];
        currentProgram.getMemory().getBytes(start, bytes);
        out.printf("BYTES\t%s\t%s\t", label, start);
        for (byte value : bytes) {
            out.printf("%02x", value & 0xff);
        }
        out.println();
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

    private Set<Address> findAlignedDwordOccurrences(long wanted) throws Exception {
        Set<Address> result = new LinkedHashSet<>();
        Memory memory = currentProgram.getMemory();
        Address cursor = currentProgram.getMinAddress();
        Address end = currentProgram.getMaxAddress();
        while (cursor.add(3).compareTo(end) <= 0) {
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
