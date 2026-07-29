// Exports static Ghidra findings for the extracted firmware.
// @category TufAio

import java.io.File;
import java.io.PrintWriter;
import java.util.HashSet;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;

public class ExportFirmwareAnalysis extends GhidraScript {
	private static final String[] TARGETS = {
		"00100000",
		"00101fb4",
		"0010d024",
		"0010ccd0",
		"0010efd0",
		"0010ee20",
		"00126d04",
		"00126814",
		"001268d0",
		"00126e00",
		"0012718c",
		"001273a8",
		"00127490",
		"001274fc",
		"00127514",
		"0012752c",
		"00127544",
		"00127558",
		"00127570",
		"00127588",
		"001275a8",
		"0012780c",
		"00127660",
		"00127854",
		"001278cc",
		"00128290",
		"00128404",
		"001284d0",
		"00128580",
		"00128bc0",
		"00128f8c",
		"00129400",
		"00129440",
		"001294ec",
		"0012967c",
		"00129690",
		"001296d8",
		"001297e8",
		"001298f8",
		"00129d84",
		"00129fd4",
		"0012a0fc",
		"0012a5ac",
		"0012a6a0",
		"0012a6d8",
		"0012a814",
		"0012b37c",
		"0012c340",
		"0012c398",
		"0012c3c0",
		"0012c40c",
		"0012c42c",
		"0012c494",
		"0012c4c0",
		"0012c4e0",
		"0012c644",
		"0012ced0",
		"0012ebb0",
		"00130820"
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
			out.println("COMPILER\t" + currentProgram.getCompilerSpec().getCompilerSpecID());
			out.println("IMAGE_BASE\t" + currentProgram.getImageBase());
			out.println("MIN_ADDRESS\t" + currentProgram.getMinAddress());
			out.println("MAX_ADDRESS\t" + currentProgram.getMaxAddress());
			out.println();

			out.println("MEMORY_BLOCKS");
			for (MemoryBlock block : currentProgram.getMemory().getBlocks()) {
				out.printf("%s\t%s\t%s\tR=%s W=%s X=%s%n",
					block.getName(), block.getStart(), block.getEnd(),
					block.isRead(), block.isWrite(), block.isExecute());
			}
			out.println();

			int functionCount = 0;
			FunctionIterator functions = currentProgram.getFunctionManager().getFunctions(true);
			while (functions.hasNext()) {
				functions.next();
				functionCount++;
			}
			out.println("FUNCTION_COUNT\t" + functionCount);
			out.println();

			out.println("DEFINED_STRINGS_OF_INTEREST");
			for (Data data : currentProgram.getListing().getDefinedData(true)) {
				Object value = data.getValue();
				if (!(value instanceof String)) {
					continue;
				}
				String text = (String) value;
				String lower = text.toLowerCase();
				if (lower.contains("usb") || lower.contains("lcd") ||
					lower.contains("boot") || lower.contains("flash") ||
					lower.contains("config") || lower.contains("jpg") ||
					lower.contains("jpeg") || lower.contains("png") ||
					lower.contains("gif") || lower.contains("emwin") ||
					lower.contains("receiving") || lower.contains("uid") ||
					lower.contains("sn:")) {
					out.printf("%s\t%s%n", data.getAddress(), text.replace("\n", "\\n"));
				}
			}
			out.println();

			DecompInterface decompiler = new DecompInterface();
			decompiler.toggleCCode(true);
			decompiler.toggleSyntaxTree(true);
			decompiler.setSimplificationStyle("decompile");
			if (!decompiler.openProgram(currentProgram)) {
				throw new IllegalStateException("decompiler could not open program");
			}

			Set<Address> decompiledEntries = new HashSet<>();
			for (String targetText : TARGETS) {
				monitor.checkCancelled();
				Address target = toAddr(targetText);
				out.println("TARGET\t" + target);

				Function function = getFunctionContaining(target);
				if (function == null) {
					function = getFunctionAt(target);
				}
				if (function == null) {
					out.println("FUNCTION\tNONE");
				}
				else {
					out.printf("FUNCTION\t%s\t%s\t%s%n",
						function.getName(), function.getEntryPoint(), function.getBody());
					out.println("CALLERS");
					ReferenceIterator refs = currentProgram.getReferenceManager()
						.getReferencesTo(function.getEntryPoint());
					while (refs.hasNext()) {
						Reference ref = refs.next();
						Function caller = getFunctionContaining(ref.getFromAddress());
						out.printf("%s\t%s\t%s%n", ref.getFromAddress(),
							caller == null ? "NO_FUNCTION" : caller.getName(),
							ref.getReferenceType());
					}
					out.println("CALLEES");
					for (Function callee : function.getCalledFunctions(monitor)) {
						out.printf("%s\t%s%n", callee.getEntryPoint(), callee.getName());
					}
				}

				out.println("REFERENCES_TO_TARGET");
				ReferenceIterator targetRefs = currentProgram.getReferenceManager().getReferencesTo(target);
				while (targetRefs.hasNext()) {
					Reference ref = targetRefs.next();
					Function caller = getFunctionContaining(ref.getFromAddress());
					out.printf("%s\t%s\t%s%n", ref.getFromAddress(),
						caller == null ? "NO_FUNCTION" : caller.getName(),
						ref.getReferenceType());
				}

				out.println("INSTRUCTION_WINDOW");
				Instruction instruction = currentProgram.getListing().getInstructionContaining(target);
				if (instruction == null) {
					instruction = currentProgram.getListing().getInstructionAfter(target.subtract(1));
				}
				for (int i = 0; instruction != null && i < 20; i++) {
					out.printf("%s\t%s%n", instruction.getAddress(), instruction);
					instruction = instruction.getNext();
				}

				if (function != null && decompiledEntries.add(function.getEntryPoint())) {
					out.println("DECOMPILE_BEGIN");
					DecompileResults results = decompiler.decompileFunction(function, 120, monitor);
					if (results.decompileCompleted()) {
						out.println(results.getDecompiledFunction().getC());
					}
					else {
						out.println("FAILED\t" + results.getErrorMessage());
					}
					out.println("DECOMPILE_END");
				}
				out.println();
			}
			decompiler.dispose();
		}
	}
}
