// Export evidence needed to reconstruct the Interface-1 LCD packet model.
// Run against the existing project with -readOnly -noanalysis. Any functions
// created for missed entry points exist only in the transient read-only session.
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

public class ExportLcdPacketModel extends GhidraScript {
    private static final String[][] TARGETS = {
        {"0010df9c", "Interface-1 EP 0x03 OUT callback"},
        {"0010e0a8", "Interface-1 EP 0x84 IN completion callback"},
        {"00115008", "USB endpoint transfer helper A"},
        {"0011508c", "USB endpoint transfer helper B"},
        {"0010dcc4", "debug-output helper adjacent to endpoint callbacks"},
        {"0010de28", "VDMA helper adjacent to endpoint callbacks"},
        {"0010deb8", "Interface-0 EP 0x01 OUT callback"},
        {"0010df88", "Interface-0 EP 0x82 IN completion callback"},
        {"001297e8", "1024-byte segmented receiver"},
        {"00128bc0", "shared 0x8108 response-template user"},
        {"00129b2c", "Interface-1 assembled-data consumer"},
        {"00129cf0", "framebuffer-ring display switch callback"},
        {"001268d0", "LCD boot and framebuffer-ring consumer"},
        {"001293f8", "transport and queue initialization"},
        {"0012a310", "queue release"},
        {"0012a390", "queue peek"},
        {"0012a3bc", "large queue initialization"},
        {"0012a3f0", "large queue allocation"},

        {"00127e9c", "display and emWin initialization callback"},
        {"0010ee20", "emWin initialization"},
        {"00110f74", "320x320 object-construction wrapper"},
        {"00111754", "320x320 object constructor"},
        {"001118e8", "constructor helper"},
        {"00109360", "display-buffer setup helper"},
        {"0010d07c", "display-buffer setup implementation"},
        {"0010e3bc", "fixed/flagged GUI allocator"},
        {"0010e628", "GUI handle lock/dereference"},
        {"0010e664", "GUI allocator free-space query"},
        {"0010e8b4", "GUI device create/link helper"},
        {"00116bc0", "GUI device bits-per-pixel query"},
        {"00116c88", "nearby-BSS timer/counter user (negative control)"},

        {"00119ee0", "0x0012ec20 table function 0"},
        {"00115db4", "0x0012ec20 table function 1"},
        {"00122ce4", "0x0012ec20 table function 2"},

        {"0011be6c", "0x001307e0 table function 0"},
        {"00120ba4", "0x001307e0 table function 1"},
        {"00120cf4", "0x001307e0 table function 2"},
        {"001217bc", "0x001307e0 table function 3"},
        {"00122d88", "0x001307e0 table function 4"},
        {"001256a8", "0x001307e0 table function 5"},
        {"001261e8", "0x001307e0 table function 6"},
        {"00125634", "0x001307e0 table function 7"},
        {"00122a70", "0x001307e0 table function 8"},
        {"00122c04", "0x001307e0 table function 9"},
        {"0012283c", "0x001307e0 table function 10"},
        {"00123090", "0x001307e0 table function 11"},
        {"001243d8", "0x001307e0 table function 12"},
        {"00124438", "0x001307e0 table function 13"},

        {"001056a4", "graphics state reset"},
        {"00105ea8", "graphics initialization used by display callback"},
        {"00105e60", "graphics completion query"},
        {"00105764", "graphics format-field helper"},
        {"001059f4", "graphics width/height source"},
        {"00105a10", "graphics transfer-state builder"},
        {"00106058", "graphics mode setter"},
        {"001060ec", "graphics operation start"},
        {"001065c4", "graphics router"},
        {"00106914", "framebuffer-ring initialization candidate"},
        {"00109394", "display framebuffer base update"},
        {"001093fc", "display enable/commit helper"},
        {"00109414", "display controller reset/setup helper"},
        {"00109578", "display configuration path"},
        {"00109620", "explicit framebuffer setup path"},
        {"0010e7f8", "emWin/display helper used during initialization"},
        {"001115b8", "emWin/display helper used during initialization"},
        {"00115110", "graphics completion callback installed by bulk path"},
        {"001141e0", "renderer pixel conversion helper"},
        {"001151e4", "renderer scanline helper"},
        {"0011acd8", "JPEG/object renderer bridge"},
        {"00109db8", "graphics helper using 0xf800 mask"},
        {"001199c4", "exact-scalar 0xf800 false-positive candidate"},
        {"001211e8", "exact-scalar 0xf800 false-positive candidate"},
        {"00126dfc", "Interface-0 command dispatcher"}
    };

    private static final long[] POINTER_VALUES = {
        0x00131314L, 0x001314d0L, 0x001307e0L, 0x0012ec20L,
        0x001315b4L, 0x0012eba0L, 0x00331b40L, 0x003bb430L,
        0x003bb480L, 0x003ed340L, 0x003edb40L, 0xb1008000L,
        0xb1008700L
    };

    private static final long[] SCALARS = {
        0x001fL, 0x003fL, 0x07e0L, 0xf800L, 0xff00L,
        0x3fcL, 0x400L, 0xc7L, 0xc8L, 0xc9L,
        0x6021L, 0x14021L, 0x32000L
    };

    private static final long[] ABSOLUTE_ADDRESSES = {
        0x0013131cL, 0x00131320L, 0x00131324L, 0x00131328L,
        0x0013132cL, 0xb100805cL, 0xb1008060L, 0xb1008700L,
        0xb100a028L, 0xb100a07cL, 0xb100a0a0L
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
            out.println("SCOPE\tread-only Interface-1 LCD packet-model export");
            out.println();

            DecompInterface decompiler = new DecompInterface();
            decompiler.toggleCCode(true);
            decompiler.toggleSyntaxTree(true);
            decompiler.setSimplificationStyle("decompile");
            if (!decompiler.openProgram(currentProgram)) {
                throw new IllegalStateException("decompiler could not open program");
            }

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
                        Address destination = ref.getToAddress();
                        out.printf("R\t%s\t%s\t%s", instruction.getAddress(), destination,
                            ref.getReferenceType());
                        Long value = readUnsignedInt(destination);
                        if (value != null) {
                            out.printf("\tDWORD=0x%08x", value);
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

            out.println("POINTER_LITERAL_XREFS");
            for (long wanted : POINTER_VALUES) {
                out.printf("POINTER\t0x%08x%n", wanted);
                for (Address literal : findAlignedDwordOccurrences(wanted)) {
                    out.printf("LITERAL\t%s%n", literal);
                    ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(literal);
                    while (refs.hasNext()) {
                        Reference ref = refs.next();
                        out.printf("XREF\t%s\t%s\t%s%n", ref.getFromAddress(),
                            describe(getFunctionContaining(ref.getFromAddress())), ref.getReferenceType());
                    }
                }
            }

            out.println("EXACT_SCALAR_USES");
            for (long wanted : SCALARS) {
                out.printf("SCALAR\t0x%x\t%d%n", wanted, wanted);
                for (Address literal : findAlignedDwordOccurrences(wanted)) {
                    out.printf("DWORD_LITERAL\t%s%n", literal);
                    ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(literal);
                    while (refs.hasNext()) {
                        Reference ref = refs.next();
                        out.printf("DWORD_XREF\t%s\t%s\t%s%n", ref.getFromAddress(),
                            describe(getFunctionContaining(ref.getFromAddress())), ref.getReferenceType());
                    }
                }
                Set<String> emitted = new LinkedHashSet<>();
                for (Instruction instruction : currentProgram.getListing().getInstructions(true)) {
                    for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
                        for (Object object : instruction.getOpObjects(operand)) {
                            if (object instanceof Scalar &&
                                ((Scalar)object).getUnsignedValue() == wanted) {
                                String line = instruction.getAddress() + "\t" +
                                    describe(getFunctionContaining(instruction.getAddress())) + "\t" +
                                    instruction;
                                if (emitted.add(line)) {
                                    out.println(line);
                                }
                            }
                        }
                    }
                }
                out.println("COUNT\t" + emitted.size());
            }

            out.println("ABSOLUTE_ADDRESS_XREFS");
            for (long value : ABSOLUTE_ADDRESSES) {
                Address destination = toAddr(value);
                out.printf("ADDRESS\t%s%n", destination);
                ReferenceIterator refs = currentProgram.getReferenceManager()
                    .getReferencesTo(destination);
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    out.printf("ADDRESS_XREF\t%s\t%s\t%s%n", ref.getFromAddress(),
                        describe(getFunctionContaining(ref.getFromAddress())),
                        ref.getReferenceType());
                }
            }

            out.println("BYTE_SWAP_INSTRUCTION_CANDIDATES");
            for (Instruction instruction : currentProgram.getListing().getInstructions(true)) {
                String mnemonic = instruction.getMnemonicString().toLowerCase();
                boolean candidate = mnemonic.equals("rev") || mnemonic.equals("rev16") ||
                    mnemonic.equals("revsh");
                if (!candidate && mnemonic.equals("ror")) {
                    String rendered = instruction.toString().toLowerCase();
                    candidate = rendered.contains("#0x8") || rendered.contains("#8");
                }
                if (candidate) {
                    out.printf("SWAP_CANDIDATE\t%s\t%s\t%s%n", instruction.getAddress(),
                        describe(getFunctionContaining(instruction.getAddress())), instruction);
                }
            }

            out.println("NEARBY_BSS_POINTER_LITERAL_XREFS");
            Memory memory = currentProgram.getMemory();
            Address cursor = currentProgram.getMinAddress();
            Address end = currentProgram.getMaxAddress();
            while (cursor.add(3).compareTo(end) <= 0) {
                monitor.checkCancelled();
                if ((cursor.getOffset() & 3) == 0 && memory.contains(cursor)) {
                    long value = Integer.toUnsignedLong(memory.getInt(cursor));
                    if (value >= 0x00131300L && value < 0x00131600L) {
                        out.printf("BSS_POINTER\t%s\t0x%08x%n", cursor, value);
                        ReferenceIterator refs = currentProgram.getReferenceManager()
                            .getReferencesTo(cursor);
                        while (refs.hasNext()) {
                            Reference ref = refs.next();
                            out.printf("BSS_XREF\t%s\t%s\t%s%n", ref.getFromAddress(),
                                describe(getFunctionContaining(ref.getFromAddress())),
                                ref.getReferenceType());
                        }
                    }
                }
                cursor = cursor.add(1);
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
