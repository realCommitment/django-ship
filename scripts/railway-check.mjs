// Evaluates .railway/railway.ts without a Railway account, so CI catches a config that no longer compiles.
import { createRailwayContext, project } from 'railway/iac';
import program from '../.railway/railway.ts';

process.env.DIRECTORY_DOMAIN ??= 'directory.example.com';
process.env.PRODUCTIVITY_DOMAIN ??= 'productivity.example.com';

const definition = await program(createRailwayContext(), project);
const names = definition.resources.flat().map((resource) => resource.name);
console.log(`railway.ts defines ${definition.name}: ${names.join(', ')}`);
