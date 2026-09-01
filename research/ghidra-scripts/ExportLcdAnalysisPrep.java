// Export bounded evidence for the next LCD/image-control analysis pass.
// This script is read-only: it does not rename, type, disassemble, or modify the program.
// @category TufAio

import java.io.File;
import java.io.PrintWriter;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ExportLcdAnalysisPrep extends GhidraScript {
	private static final int MAX_PATH_DEPTH = 10;
	private static final long[] SCALARS = {
		0x140, 0x190, 0x1b4, 0x1b8, 0x3fc, 0x400, 0x32000
	};

	private static final String[][] TARGETS = {
		{"0010ccd0", "LCM initialization"},
		{"0010cc90", "LCM low-level write candidate"},
		{"0010df9c", "interface-1 endpoint-3 OUT callback"},
		{"0010ee20", "SEGGER emWin initialization"},
		{"001056a4", "interface-0 command-0x08 callee"},
		{"00106058", "graphics-router operation 0x08 callee"},
		{"001060ec", "graphics-router operation 0x0c callee"},
		{"001063d4", "coordinate/block graphics candidate"},
		{"00106444", "graphics state/buffer candidate"},
		{"001065c4", "interface-0 command-0x08 repeated callee"},
		{"00109388", "interface-0 command-0x08 value source"},
		{"0010ed1c", "command-0x09 0x140 callee"},
		{"0010eff4", "centered object/image draw candidate"},
		{"0010f0d0", "object/image dimensions candidate"},
		{"00110f74", "320x320 display/framebuffer constructor candidate"},
		{"001115b8", "command-0x09 callee"},
		{"00113abc", "320x320 layer/viewport setup candidate"},
		{"0011305c", "command-0x09 callee"},
		{"00116774", "emWin 320-sized initialization"},
		{"0011acd8", "shared object/image-to-graphics bridge"},
		{"001268d0", "LCD boot process"},
		{"00126dfc", "interface-0 device dispatcher"},
		{"00127660", "SPI/config initialization"},
		{"00127854", "boot/JPG default-path owner"},
		{"001279e8", "LCD boot/display-state callback"},
		{"00127e9c", "emWin caller"},
		{"00128290", "object/data query used by dispatcher"},
		{"00128404", "command-0x0a allocation/write abstraction"},
		{"001284d0", "command-0x0b block write abstraction"},
		{"00128580", "command-0x0b finalize abstraction"},
		{"00128bc0", "command-0x88 SPI path"},
		{"001293f8", "interface-0 transport dispatcher"},
		{"001296d8", "440-byte segmented receiver"},
		{"001297e8", "1024-byte segmented receiver"},
		{"001298f8", "440-byte response builder"},
		{"00129b2c", "large-data graphics consumer candidate"},
		{"0012a5ac", "SPI initialization/ID"},
		{"0012a6d8", "SPI read"},
		{"0012a814", "SPI write"}
	};

	private static final String[][] PATH_SOURCES = {
		{"0010df9c", "interface-1 endpoint callback"},
		{"00126dfc", "interface-0 dispatcher"},
		{"001056a4", "command-0x08 first callee"},
		{"001065c4", "command-0x08 repeated callee"},
		{"0010ed1c", "command-0x09 0x140 callee"},
		{"00127e9c", "emWin caller"}
	};

	private static final String[][] PATH_TARGETS = {
		{"0010ccd0", "LCM init"},
		{"0010cc90", "LCM low-level write"},
		{"0010ee20", "emWin init"},
		{"001297e8", "1024-byte receiver"},
		{"0012a6d8", "SPI read"},
		{"0012a814", "SPI write"}
	};

	private static class PathNode {
		final Function function;
		final List<Function> path;
		PathNode(Function function, List<Function> path) {
			this.function = function;
			this.path = path;
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

		try (PrintWriter out = new PrintWriter(output, "UTF-8")) {
			out.println("PROGRAM\t" + currentProgram.getName());
			out.println("LANGUAGE\t" + currentProgram.getLanguageID());
			out.println("SCOPE\tbounded read-only static export; no analysis or program changes");
			out.println();

			DecompInterface decompiler = new DecompInterface();
			decompiler.toggleCCode(true);
			decompiler.toggleSyntaxTree(true);
			decompiler.setSimplificationStyle("decompile");
			if (!decompiler.openProgram(currentProgram)) {
				throw new IllegalStateException("decompiler could not open program");
			}

			for (String[] spec : TARGETS) {
				monitor.checkCancelled();
				Function function = functionAt(spec[0]);
				out.printf("TARGET\t%s\t%s\t%s%n", spec[0], spec[1], describe(function));
				if (function == null) {
					out.println("INSTRUCTIONS_BEGIN");
					Instruction instruction = currentProgram.getListing()
						.getInstructionAt(toAddr(spec[0]));
					for (int i = 0; instruction != null && i < 96; i++) {
						out.printf("%s\t%s%n", instruction.getAddress(), instruction);
						instruction = instruction.getNext();
					}
					out.println("INSTRUCTIONS_END");
					out.println();
					continue;
				}
				out.println("CALLERS");
				ReferenceIterator refs = currentProgram.getReferenceManager()
					.getReferencesTo(function.getEntryPoint());
				while (refs.hasNext()) {
					Reference ref = refs.next();
					Function caller = getFunctionContaining(ref.getFromAddress());
					out.printf("%s\t%s\t%s%n", ref.getFromAddress(),
						caller == null ? "NO_FUNCTION" : describe(caller), ref.getReferenceType());
				}
				out.println("CALLEES");
				for (Function callee : function.getCalledFunctions(monitor)) {
					out.println(describe(callee));
				}
				out.println("DECOMPILE_BEGIN");
				DecompileResults results = decompiler.decompileFunction(function, 120, monitor);
				if (results.decompileCompleted()) {
					out.println(results.getDecompiledFunction().getC());
				}
				else {
					out.println("FAILED\t" + results.getErrorMessage());
				}
				out.println("DECOMPILE_END");
				out.println();
			}
			decompiler.dispose();

			out.println("STATIC_SHORTEST_PATHS");
			for (String[] sourceSpec : PATH_SOURCES) {
				Function source = functionAt(sourceSpec[0]);
				for (String[] targetSpec : PATH_TARGETS) {
					Function target = functionAt(targetSpec[0]);
					out.printf("PATH\t%s:%s\t%s:%s", sourceSpec[0], sourceSpec[1],
						targetSpec[0], targetSpec[1]);
					List<Function> path = findPath(source, target);
					if (path == null) {
						out.println("\tNOT_FOUND");
					}
					else {
						for (Function step : path) {
							out.print("\t" + describe(step));
						}
						out.println();
					}
				}
			}
			out.println();

			out.println("EXACT_SCALAR_USES");
			for (long wanted : SCALARS) {
				out.printf("SCALAR\t0x%x\t%d%n", wanted, wanted);
				int count = 0;
				for (Instruction instruction : currentProgram.getListing().getInstructions(true)) {
					for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
						for (Object object : instruction.getOpObjects(operand)) {
							if (object instanceof Scalar && ((Scalar)object).getUnsignedValue() == wanted) {
								Function owner = getFunctionContaining(instruction.getAddress());
								out.printf("%s\t%s\t%s%n", instruction.getAddress(),
									owner == null ? "NO_FUNCTION" : describe(owner), instruction);
								count++;
							}
						}
					}
				}
				out.println("COUNT\t" + count);
			}
		}
	}

	private Function functionAt(String text) {
		Address address = toAddr(text);
		Function function = getFunctionAt(address);
		return function != null ? function : getFunctionContaining(address);
	}

	private String describe(Function function) {
		return function == null ? "NO_FUNCTION" :
			function.getEntryPoint() + ":" + function.getName();
	}

	private List<Function> findPath(Function source, Function target) throws Exception {
		if (source == null || target == null) {
			return null;
		}
		ArrayDeque<PathNode> queue = new ArrayDeque<>();
		Set<Address> visited = new HashSet<>();
		List<Function> initial = new ArrayList<>();
		initial.add(source);
		queue.add(new PathNode(source, initial));
		visited.add(source.getEntryPoint());
		while (!queue.isEmpty()) {
			monitor.checkCancelled();
			PathNode node = queue.removeFirst();
			if (node.function.getEntryPoint().equals(target.getEntryPoint())) {
				return node.path;
			}
			if (node.path.size() - 1 >= MAX_PATH_DEPTH) {
				continue;
			}
			for (Function callee : node.function.getCalledFunctions(monitor)) {
				if (!visited.add(callee.getEntryPoint())) {
					continue;
				}
				List<Function> next = new ArrayList<>(node.path);
				next.add(callee);
				queue.addLast(new PathNode(callee, next));
			}
		}
		return null;
	}
}
